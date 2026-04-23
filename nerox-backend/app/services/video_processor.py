"""
app/services/video_processor.py
==================================
OpenCV-based video frame extraction for the Nerox AI fingerprinting engine.

Strategy: Interval-based keyframe extraction
--------------------------------------------
  - Reads video FPS from container metadata
  - Calculates frame step = fps × FRAME_INTERVAL_SEC
  - Reads every Nth frame (skips the rest without decoding)
  - Caps total extracted frames at MAX_FRAMES for memory safety
  - Applies the same resize + BGR→RGB preprocessing as ImageProcessor

Why interval-based (not scene-detection)?
  - Deterministic: same video always produces the same keyframes
  - Fast: no optical-flow or histogram computation overhead
  - Robust: works on all codecs OpenCV supports
  - Sufficient: for content protection matching, 1 fps coverage is accurate

Design Notes
------------
This module is stateless and thread-safe (pure OpenCV operations).
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import cv2
import numpy as np

from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

FRAME_INTERVAL_SEC: float = 1.0       # extract 1 frame per second of video
MAX_FRAMES: int           = 120       # hard cap: ~2 min at 1 fps
MODEL_INPUT_SIZE: tuple[int, int] = (224, 224)


# ---------------------------------------------------------------------------
# VideoProcessor class
# ---------------------------------------------------------------------------

class VideoProcessor:
    """
    Interval-based keyframe extractor using OpenCV VideoCapture.

    Fully stateless — safe to call from multiple background threads.
    """

    def extract_key_frames(
        self,
        file_path: str,
        frame_interval_sec: float = FRAME_INTERVAL_SEC,
        max_frames: int           = MAX_FRAMES,
    ) -> List[np.ndarray]:
        """
        Extract keyframes from a video file at regular time intervals.

        Each extracted frame is:
          - Resized to MODEL_INPUT_SIZE (224 × 224) with Lanczos interpolation
          - Converted from BGR → RGB

        Args:
            file_path:          Absolute or relative path to the video file.
            frame_interval_sec: Time between extracted frames in seconds (default 1.0).
            max_frames:         Maximum number of frames to extract (default 120).

        Returns:
            List of (224, 224, 3) uint8 RGB numpy arrays.
            Minimum length is 1 (at least the first valid frame).

        Raises:
            ValueError: If the file does not exist, cannot be opened by OpenCV,
                        or yields zero readable frames.
        """
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"Video file not found: {file_path}")

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise ValueError(
                f"OpenCV cannot open video at: {file_path}. "
                "The container format may be unsupported or the file corrupted."
            )

        # ── Read container metadata ──────────────────────────────────────────
        fps           = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec  = total_frames / fps if fps > 0 else 0.0

        # Frames to skip between each sampled frame
        frame_step    = max(1, int(round(fps * frame_interval_sec)))

        logger.info(
            "Video '%s' — fps=%.2f | total_frames=%d | duration=%.1fs | step=%d",
            path.name, fps, total_frames, duration_sec, frame_step,
        )

        frames: List[np.ndarray] = []
        raw_idx = 0

        while len(frames) < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if raw_idx % frame_step == 0:
                preprocessed = self._preprocess_frame(frame, path.name, raw_idx)
                if preprocessed is not None:
                    frames.append(preprocessed)

            raw_idx += 1

        cap.release()

        if not frames:
            raise ValueError(
                f"Zero usable frames could be extracted from: {file_path}. "
                "The video may be empty or in an incompatible codec."
            )

        logger.info(
            "Extracted %d keyframes from '%s' (%.1fs video)",
            len(frames), path.name, duration_sec,
        )
        return frames

    def _preprocess_frame(
        self,
        frame_bgr: np.ndarray,
        filename:  str,
        frame_idx: int,
    ) -> np.ndarray | None:
        """
        Resize one BGR frame to MODEL_INPUT_SIZE and convert to RGB.

        Returns None on any processing failure so the frame is silently
        skipped without aborting the whole extraction.

        Args:
            frame_bgr: Raw BGR frame from cv2.VideoCapture.read().
            filename:  Video filename (for logging only).
            frame_idx: Frame index within the video (for logging only).

        Returns:
            (224, 224, 3) RGB uint8 array, or None on failure.
        """
        try:
            if frame_bgr is None or frame_bgr.size == 0:
                logger.debug("Skipping empty frame %d in '%s'", frame_idx, filename)
                return None

            resized = cv2.resize(
                frame_bgr, MODEL_INPUT_SIZE, interpolation=cv2.INTER_LANCZOS4
            )
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            return rgb

        except Exception as exc:
            logger.warning(
                "Frame %d preprocessing failed in '%s': %s",
                frame_idx, filename, exc,
            )
            return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_video_processor: VideoProcessor | None = None


def get_video_processor() -> VideoProcessor:
    """Return the process-level VideoProcessor singleton."""
    global _video_processor
    if _video_processor is None:
        _video_processor = VideoProcessor()
    return _video_processor
