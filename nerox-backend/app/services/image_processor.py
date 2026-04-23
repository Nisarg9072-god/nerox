"""
app/services/image_processor.py
=================================
OpenCV-based image preprocessing pipeline for the Nerox AI fingerprinting engine.

Responsibilities
----------------
  - Load image from disk with validation
  - Resize to model input size using high-quality interpolation
  - Convert BGR → RGB for PyTorch/ImageNet convention
  - Return preprocessed numpy array ready for EmbeddingService

Design Notes
------------
This module is intentionally kept stateless (pure functions + singleton class)
so it can be safely used from multiple threads in the BackgroundTask executor.
All OpenCV operations are CPU-bound and thread-safe.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_INPUT_SIZE: tuple[int, int] = (224, 224)  # ResNet50 expected input


# ---------------------------------------------------------------------------
# ImageProcessor class
# ---------------------------------------------------------------------------

class ImageProcessor:
    """
    Stateless image preprocessing utility.

    Can be safely instantiated once and called from multiple threads
    (all operations are pure numpy/OpenCV, no shared mutable state).
    """

    def load_and_validate(self, file_path: str) -> np.ndarray:
        """
        Load image from disk using OpenCV and validate its structure.

        Args:
            file_path: Absolute or relative path to the image file.

        Returns:
            Raw BGR numpy array of shape (H, W, 3), dtype uint8.

        Raises:
            ValueError: If the file does not exist, cannot be read by OpenCV,
                        or has an unexpected channel layout.
        """
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"Image file not found: {file_path}")

        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(
                f"OpenCV cannot decode image at: {file_path}. "
                "The file may be corrupted or in an unsupported format."
            )

        # Sanity-check: must be a 3-channel colour image
        if img.ndim != 3 or img.shape[2] != 3:
            raise ValueError(
                f"Unexpected image shape {img.shape} for '{path.name}'. "
                "Expected a 3-channel (BGR) colour image."
            )

        logger.debug(
            "Loaded image: %s — shape=%s dtype=%s",
            path.name, img.shape, img.dtype,
        )
        return img

    def preprocess(self, file_path: str) -> np.ndarray:
        """
        Full preprocessing pipeline for one image file.

        Steps:
          1. Load and validate the image from disk.
          2. Resize to MODEL_INPUT_SIZE (224 × 224) with Lanczos interpolation.
          3. Convert BGR → RGB (ImageNet/PyTorch convention).

        Tensor conversion and per-channel ImageNet normalisation are handled
        by EmbeddingService to keep responsibilities cleanly separated.

        Args:
            file_path: Absolute or relative path to the image.

        Returns:
            Preprocessed (224, 224, 3) RGB uint8 numpy array.

        Raises:
            ValueError: If the image cannot be loaded or is invalid.
        """
        img = self.load_and_validate(file_path)

        # High-quality resize — Lanczos preserves fine texture detail
        resized = cv2.resize(img, MODEL_INPUT_SIZE, interpolation=cv2.INTER_LANCZOS4)

        # BGR (OpenCV native) → RGB (ImageNet/torchvision convention)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        logger.debug(
            "Preprocessed: %s → shape=%s", Path(file_path).name, rgb.shape
        )
        return rgb


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_image_processor: ImageProcessor | None = None


def get_image_processor() -> ImageProcessor:
    """Return the process-level ImageProcessor singleton."""
    global _image_processor
    if _image_processor is None:
        _image_processor = ImageProcessor()
    return _image_processor
