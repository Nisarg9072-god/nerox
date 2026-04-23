"""
app/services/embedding_service.py
===================================
ResNet50-based deep feature extraction for the Nerox AI fingerprinting engine.

Architecture
------------
EmbeddingService holds a singleton ResNet50 backbone (final FC layer removed)
loaded with official IMAGENET1K_V1 pretrained weights. The backbone outputs a
2048-dimensional global average pooled feature vector.

All vectors are L2-normalised before return so that:
    inner_product(a_norm, b_norm) == cosine_similarity(a, b)

This property is required by FAISS IndexFlatIP.

Aggregation for multi-frame inputs (video)
------------------------------------------
  1. Each frame is embedded independently           → (N, 2048) matrix
  2. Mean-pooled across the frame axis              → (2048,) vector
  3. Re-normalised                                  → unit-length

Mean pooling is more robust than max-pooling for content-matching tasks
because it captures the overall visual character rather than dominant peaks.

Model constants (importable without triggering torch)
------------------------------------------------------
  MODEL_NAME        = "ResNet50"
  MODEL_WEIGHTS     = "IMAGENET1K_V1"
  MODEL_VERSION     = "1.0"
  EMBEDDING_DIM     = 2048
  MODEL_IDENTIFIER  = "ResNet50-IMAGENET1K_V1-v1.0"
"""

from __future__ import annotations

import time
from typing import List, Optional, Tuple

import numpy as np

from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Model constants — importable without triggering torch
# ---------------------------------------------------------------------------

MODEL_NAME       = "ResNet50"
MODEL_WEIGHTS    = "IMAGENET1K_V1"
MODEL_VERSION    = "1.0"
EMBEDDING_DIM    = 2048
MODEL_IDENTIFIER = f"{MODEL_NAME}-{MODEL_WEIGHTS}-v{MODEL_VERSION}"

# ImageNet channel-wise mean and std (used during ResNet50 training)
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)


# ---------------------------------------------------------------------------
# EmbeddingService class
# ---------------------------------------------------------------------------

class EmbeddingService:
    """
    Singleton ResNet50 feature extractor with lazy model loading.

    The PyTorch model is downloaded and loaded on the first call to
    get_model(), then cached in memory for the lifetime of the process.
    Subsequent calls skip loading and reuse the cached instance.

    Thread safety: PyTorch inference with torch.no_grad() is thread-safe
    in CPU mode. The model is shared across background task threads.
    """

    def __init__(self) -> None:
        self._model  = None
        self._device: Optional[str] = None

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def get_model(self) -> Tuple:
        """
        Load and cache the ResNet50 backbone (call once, reuse forever).

        Returns:
            (model, device) — the backbone nn.Sequential and device string.

        Raises:
            RuntimeError: If torch or torchvision are not installed.
        """
        if self._model is not None:
            return self._model, self._device

        try:
            import torch
            import torch.nn as nn
            import torchvision.models as models
        except ImportError:
            raise RuntimeError(
                "torch and torchvision are required for fingerprinting. "
                "Install with: pip install torch torchvision"
            )

        t0 = time.perf_counter()
        logger.info(
            "Loading %s with weights=%s …", MODEL_NAME, MODEL_WEIGHTS
        )

        # Full ResNet50 (with pretrained ImageNet1K_V1 weights)
        base = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1)

        # Remove the final FC classification layer.
        # After GlobalAveragePooling the output shape is (batch, 2048, 1, 1).
        backbone = nn.Sequential(*list(base.children())[:-1])
        backbone.eval()  # disable BatchNorm/Dropout training behaviour

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model  = backbone.to(self._device)

        elapsed = time.perf_counter() - t0
        logger.info(
            "%s backbone ready on %s (loaded in %.2fs)", MODEL_NAME, self._device, elapsed
        )
        return self._model, self._device

    # ------------------------------------------------------------------
    # Frame normalisation — numpy → tensor
    # ------------------------------------------------------------------

    def _to_tensor(self, rgb_frame: np.ndarray):
        """
        Apply ImageNet normalisation and return a PyTorch tensor on device.

        Input:  (224, 224, 3) uint8 RGB numpy array
        Output: (1, 3, 224, 224) float32 tensor on self._device
        """
        import torch

        # uint8 [0, 255] → float32 [0.0, 1.0]
        frame = rgb_frame.astype(np.float32) / 255.0

        # Per-channel subtract mean, divide by std (ImageNet statistics)
        frame = (frame - _IMAGENET_MEAN) / _IMAGENET_STD

        # (H, W, C) → (C, H, W) → (1, C, H, W)  [batch dimension]
        tensor = torch.from_numpy(frame.transpose(2, 0, 1)).unsqueeze(0)
        return tensor.to(self._device)

    # ------------------------------------------------------------------
    # Single-frame embedding
    # ------------------------------------------------------------------

    def embed_frame(self, rgb_frame: np.ndarray) -> np.ndarray:
        """
        Extract a 2048-d L2-normalised embedding from one preprocessed frame.

        Args:
            rgb_frame: (224, 224, 3) uint8 RGB numpy array.
                       Produced by ImageProcessor.preprocess() or
                       VideoProcessor._preprocess_frame().

        Returns:
            (2048,) float32 L2-normalised numpy array (unit length).
        """
        import torch

        model, _ = self.get_model()
        tensor   = self._to_tensor(rgb_frame)

        with torch.no_grad():
            out = model(tensor)                           # (1, 2048, 1, 1)

        vec = out.squeeze().cpu().numpy().astype(np.float32)  # (2048,)
        return self._l2_normalise(vec)

    # ------------------------------------------------------------------
    # Multi-frame aggregation (video)
    # ------------------------------------------------------------------

    def embed_frames(self, rgb_frames: List[np.ndarray]) -> np.ndarray:
        """
        Generate a single embedding for a sequence of video frames
        via mean-pooling followed by re-normalisation.

        Process:
          1. Embed each frame independently  → (N, 2048) matrix
          2. Mean across frame axis          → (2048,) vector
          3. L2 re-normalise                 → unit length

        Args:
            rgb_frames: List of (224, 224, 3) uint8 RGB numpy arrays.

        Returns:
            (2048,) float32 L2-normalised numpy array.

        Raises:
            ValueError: If rgb_frames is empty.
        """
        if not rgb_frames:
            raise ValueError("embed_frames received an empty frame list.")

        t0 = time.perf_counter()
        per_frame = np.stack(
            [self.embed_frame(f) for f in rgb_frames], axis=0
        )  # (N, 2048)

        mean_vec = per_frame.mean(axis=0)  # (2048,)
        result   = self._l2_normalise(mean_vec)

        elapsed = time.perf_counter() - t0
        logger.debug(
            "embed_frames: %d frames aggregated in %.2fs", len(rgb_frames), elapsed
        )
        return result

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _l2_normalise(vec: np.ndarray) -> np.ndarray:
        """Normalise a vector to unit length. No-op if norm is near zero."""
        norm = np.linalg.norm(vec)
        if norm < 1e-9:
            logger.warning("Near-zero vector norm detected — returning unnormalised vector.")
            return vec.astype(np.float32)
        return (vec / norm).astype(np.float32)

    @property
    def model_identifier(self) -> str:
        """Human-readable model identifier string."""
        return MODEL_IDENTIFIER

    @property
    def is_loaded(self) -> bool:
        """True if the model weights have been loaded into memory."""
        return self._model is not None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """
    Return the process-level EmbeddingService singleton.

    The model is NOT loaded here; it loads lazily on first embed_frame() call.
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
