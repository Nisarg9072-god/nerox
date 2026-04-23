"""
app/services/video_watermark.py
================================
Frame-level invisible watermark embedding and extraction for video files.

Strategy
--------
Embedding:
  - Read all frames with cv2.VideoCapture.
  - Embed the DCT watermark (from image_watermark) into every
    WATERMARK_FRAME_INTERVAL-th frame; remaining frames are passed through
    unchanged.
  - Write output with cv2.VideoWriter (mp4v codec, lossless-ish intermediary).
  - On success: atomically rename temp file over the input (overwrite in place).

Extraction:
  - Sample SAMPLE_FRAME_COUNT frames evenly across the video timeline.
  - Attempt watermark extraction from each frame.
  - Keep frames where extraction confidence ≥ MIN_FRAME_CONFIDENCE.
  - Return majority-voted 64-bit token and mean confidence across valid frames.

Robustness
----------
  - Watermarking every other frame (interval=2) means the watermark survives
    moderate temporal clipping (removing up to 50% of content from either end
    while still leaving watermarked frames).
  - Extraction only needs ONE high-confidence frame to succeed.
  - For full-length videos, 10 sample frames provides redundancy.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

from app.core.logger import get_logger
from app.services.image_watermark import (
    WM_BITS,
    MIN_DIM,
    embed_watermark,
    extract_watermark,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WATERMARK_FRAME_INTERVAL: int   = 2    # embed watermark every N frames
SAMPLE_FRAME_COUNT:       int   = 10   # frames sampled during extraction
MIN_FRAME_CONFIDENCE:     float = 0.45 # minimum confidence to count a frame


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def embed_watermark_to_video(
    file_path:   str,
    wm_token:    bytes,
    output_path: str | None = None,
) -> str:
    """
    Embed an 8-byte watermark token into a video file frame-by-frame.

    Every WATERMARK_FRAME_INTERVAL-th frame is watermarked using DCT.
    The modified stream is written to a temporary file, then atomically
    renamed to replace the original (or written to output_path).

    Args:
        file_path:   Path to the input video (mp4 / mov).
        wm_token:    8-byte watermark token.
        output_path: Destination path.  None → overwrite file_path in place.

    Returns:
        Path to the saved watermarked video.

    Raises:
        ValueError: If the video cannot be opened or contains zero frames.
        IOError:    If VideoWriter cannot be created.
    """
    path   = Path(file_path)
    suffix = path.suffix.lower() or ".mp4"
    tmp    = str(path.parent / (path.stem + "_wm_tmp" + suffix))

    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        raise ValueError(f"cv2.VideoCapture cannot open: {file_path}")

    fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")

    out = cv2.VideoWriter(tmp, fourcc, fps, (width, height))
    if not out.isOpened():
        cap.release()
        raise IOError(f"cv2.VideoWriter cannot create output: {tmp}")

    can_wm      = (width >= MIN_DIM and height >= MIN_DIM)
    frame_idx   = 0
    n_embedded  = 0

    if not can_wm:
        logger.warning(
            "Video frames (%dx%d) are below MIN_DIM=%d — "
            "watermark skipped, passing frames through unchanged.",
            width, height, MIN_DIM,
        )

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if can_wm and (frame_idx % WATERMARK_FRAME_INTERVAL == 0):
            try:
                frame = embed_watermark(frame, wm_token)
                n_embedded += 1
            except Exception as exc:
                logger.warning("Frame %d watermarking failed: %s", frame_idx, exc)

        out.write(frame)
        frame_idx += 1

    cap.release()
    out.release()

    if frame_idx == 0:
        Path(tmp).unlink(missing_ok=True)
        raise ValueError(f"Video has zero readable frames: {file_path}")

    # Atomic replacement
    dest = output_path if output_path else file_path
    Path(tmp).replace(dest)

    logger.info(
        "Video watermarked: '%s' | frames=%d watermarked=%d (every %d)",
        path.name, frame_idx, n_embedded, WATERMARK_FRAME_INTERVAL,
    )
    return dest


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_watermark_from_video(file_path: str) -> Tuple[bytes, float]:
    """
    Extract the embedded watermark token from a video by sampling frames.

    Samples SAMPLE_FRAME_COUNT frames spread evenly across the video.
    Applies the DCT extraction algorithm to each frame.
    Uses majority vote across all high-confidence frames.

    Args:
        file_path: Path to the suspicious video file.

    Returns:
        (wm_token, confidence):
          wm_token   — 8-byte extracted token.
          confidence — float [0, 1]; bit-level agreement across valid frames.

    Raises:
        ValueError: If video cannot be opened.
    """
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        raise ValueError(f"cv2.VideoCapture cannot open: {file_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames < 1:
        cap.release()
        logger.warning("Video appears empty: %s", file_path)
        return b"\x00" * (WM_BITS // 8), 0.0

    n_samples   = min(SAMPLE_FRAME_COUNT, total_frames)
    sample_pos  = np.linspace(0, total_frames - 1, n_samples, dtype=int)

    bits_list:  List[np.ndarray] = []
    conf_list:  List[float]       = []

    for pos in sample_pos:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(pos))
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        h, w = frame.shape[:2]
        if h < MIN_DIM or w < MIN_DIM:
            continue

        try:
            token, conf = extract_watermark(frame)
            if conf >= MIN_FRAME_CONFIDENCE:
                raw = np.unpackbits(
                    np.frombuffer(token, dtype=np.uint8)
                ).astype(np.int32)[:WM_BITS]
                bits_list.append(raw)
                conf_list.append(conf)
        except Exception as exc:
            logger.debug("Frame %d extraction error: %s", pos, exc)

    cap.release()

    if not bits_list:
        logger.warning("No usable watermark frames in: %s", file_path)
        return b"\x00" * (WM_BITS // 8), 0.0

    bits_matrix = np.stack(bits_list, axis=0)  # (n_valid, 64)
    n_valid     = bits_matrix.shape[0]

    votes      = bits_matrix.sum(axis=0)       # (64,)
    majority   = (votes > n_valid / 2).astype(np.uint8)
    unanimous  = (votes == n_valid) | (votes == 0)
    confidence = float(unanimous.mean())

    token = np.packbits(majority).tobytes()[: WM_BITS // 8]

    logger.info(
        "Video watermark extracted: token=%s confidence=%.3f valid_frames=%d/%d",
        token.hex(), confidence, n_valid, n_samples,
    )
    return token, confidence
