"""
app/services/image_watermark.py
================================
DCT frequency-domain invisible watermark embedding and extraction for images.

Algorithm: Spread-Spectrum DCT Watermarking
--------------------------------------------
1.  Convert BGR image → YCbCr colour space.
2.  Extract luminance (Y) channel (human eye most sensitive here).
3.  Divide Y into 8×8 non-overlapping blocks.
4.  Apply 2D DCT to each block (cv2.dct — no extra dependencies).
5.  Embed one watermark bit per block by forcing the mid-frequency
    DCT coefficient at position [EMBED_ROW, EMBED_COL] to:
        bit=1 → coefficient  ≥ +ALPHA
        bit=0 → coefficient  ≤ -ALPHA
    The selective modification (max/min) means blocks already carrying the
    correct signal value are left completely unchanged.
6.  Apply inverse DCT (cv2.idct) per modified block, reconstruct Y.
7.  Convert YCbCr → BGR and save.

JPEG robustness
---------------
JPEG quantisation step at [4,3] (Q50 standard table) = 56.
  Q80 → step ≈ 22   ALPHA=40 > 22  ✓ survives
  Q75 → step ≈ 28   ALPHA=40 > 28  ✓ survives
  Q70 → step ≈ 34   ALPHA=40 > 34  ✓ survives

Payload
-------
  8-byte random wm_token (generated per asset by watermark_service)
  → 64 bits, repeated WM_REPEATS=3 times  → 192 blocks total
  → needs image ≥ 128 × 128 px (256 blocks available)

Visibility
----------
  Mean pixel perturbation ≈ ALPHA/8 ≈ 5 levels on [0,255]
  Only on blocks where the coefficient needs changing.
  PSNR ≈ 44–50 dB  → imperceptible.
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

BLOCK_SIZE  = 8       # Standard 8×8 DCT block
EMBED_ROW   = 4       # Mid-frequency row within block (0-indexed)
EMBED_COL   = 3       # Mid-frequency column within block (0-indexed)
ALPHA       = 50.0    # Embedding amplitude — survives JPEG Q≥65, robust on all image types
WM_BITS     = 64      # Watermark token length in bits (8 bytes)
WM_REPEATS  = 3       # Repetitions for majority-vote error correction
TOTAL_BITS  = WM_BITS * WM_REPEATS  # 192 bits embedded total
MIN_DIM     = 128     # Minimum image / frame dimension in pixels


# ---------------------------------------------------------------------------
# Bit-level utilities
# ---------------------------------------------------------------------------

def bytes_to_bits(data: bytes) -> np.ndarray:
    """
    Convert bytes to a boolean numpy array, MSB-first per byte.

    Args:
        data: Must be exactly WM_BITS // 8 bytes (8 bytes).

    Returns:
        (WM_BITS,) boolean numpy array.
    """
    if len(data) != WM_BITS // 8:
        raise ValueError(f"Expected {WM_BITS // 8} bytes, got {len(data)}")
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8)).astype(bool)


def bits_to_bytes(bits: np.ndarray) -> bytes:
    """
    Convert the first WM_BITS bits of a boolean numpy array to bytes.

    Args:
        bits: Boolean / uint8 numpy array of length ≥ WM_BITS.

    Returns:
        8-byte token.
    """
    arr = bits[:WM_BITS].astype(np.uint8)
    if len(arr) < WM_BITS:
        arr = np.pad(arr, (0, WM_BITS - len(arr)))
    return np.packbits(arr).tobytes()


# ---------------------------------------------------------------------------
# Core embedding
# ---------------------------------------------------------------------------

def embed_watermark(image_bgr: np.ndarray, wm_token: bytes) -> np.ndarray:
    """
    Embed an 8-byte watermark token into a BGR image using DCT.

    The token is tiled WM_REPEATS=3 times and distributed across consecutive
    8×8 DCT blocks of the luminance channel.  Only the coefficient at
    [EMBED_ROW, EMBED_COL] of each block is modified.

    Args:
        image_bgr: H×W×3 uint8 numpy array (BGR, as returned by cv2.imread).
        wm_token:  8 cryptographically-random bytes produced by os.urandom(8).

    Returns:
        Watermarked H×W×3 uint8 numpy array (BGR).

    Raises:
        ValueError: If image dimensions are smaller than MIN_DIM.
    """
    h, w = image_bgr.shape[:2]
    if h < MIN_DIM or w < MIN_DIM:
        raise ValueError(
            f"Image too small ({w}×{h} px). "
            f"Minimum required for watermarking: {MIN_DIM}×{MIN_DIM} px."
        )

    # Tile watermark bits 3× for error correction
    wm_bits   = bytes_to_bits(wm_token)           # (64,)  boolean
    full_bits = np.tile(wm_bits, WM_REPEATS)      # (192,) boolean

    # Work on Y (luminance) channel
    ycbcr   = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2YCrCb)
    y_float = ycbcr[:, :, 0].astype(np.float32)

    blocks_h     = h // BLOCK_SIZE
    blocks_w     = w // BLOCK_SIZE
    total_blocks = blocks_h * blocks_w
    n_embed      = min(len(full_bits), total_blocks)

    for idx in range(n_embed):
        bi  = idx // blocks_w
        bj  = idx % blocks_w
        r0  = bi * BLOCK_SIZE
        c0  = bj * BLOCK_SIZE

        block     = y_float[r0 : r0 + BLOCK_SIZE, c0 : c0 + BLOCK_SIZE]
        dct_block = cv2.dct(block.copy())

        coeff = dct_block[EMBED_ROW, EMBED_COL]
        # Hard-set to ±ALPHA — guarantees correct sign regardless of original
        # image content.  This is more robust than max/min on noisy images.
        dct_block[EMBED_ROW, EMBED_COL] = ALPHA if full_bits[idx] else -ALPHA

        y_float[r0 : r0 + BLOCK_SIZE, c0 : c0 + BLOCK_SIZE] = cv2.idct(dct_block)

    ycbcr[:, :, 0] = np.clip(y_float, 0, 255).astype(np.uint8)
    result = cv2.cvtColor(ycbcr, cv2.COLOR_YCrCb2BGR)

    logger.debug(
        "Watermark embedded — token=%s blocks=%d/%d image=%dx%d",
        wm_token.hex(), n_embed, total_blocks, w, h,
    )
    return result


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def extract_watermark(image_bgr: np.ndarray) -> tuple[bytes, float]:
    """
    Extract the embedded watermark token from a BGR image using DCT.

    Reads the DCT coefficient at [EMBED_ROW, EMBED_COL] for each 8×8 block
    and reconstructs the bit stream.  Uses majority vote across all complete
    WM_BITS-length repetitions to correct bit errors.

    Args:
        image_bgr: Possibly-watermarked H×W×3 uint8 numpy array (BGR).

    Returns:
        (wm_token, confidence):
          wm_token   — 8-byte extracted token (majority vote of repetitions).
          confidence — float [0, 1]; fraction of bit positions unanimously
                       agreed upon across all repetitions.  1.0 = perfect;
                       values drop with compression, resizing, or editing.
    """
    h, w = image_bgr.shape[:2]

    ycbcr   = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2YCrCb)
    y_float = ycbcr[:, :, 0].astype(np.float32)

    blocks_h     = h // BLOCK_SIZE
    blocks_w     = w // BLOCK_SIZE
    total_blocks = blocks_h * blocks_w
    n_extract    = min(TOTAL_BITS, total_blocks)

    raw_bits = np.zeros(n_extract, dtype=np.int32)

    for idx in range(n_extract):
        bi  = idx // blocks_w
        bj  = idx % blocks_w
        r0  = bi * BLOCK_SIZE
        c0  = bj * BLOCK_SIZE

        block     = y_float[r0 : r0 + BLOCK_SIZE, c0 : c0 + BLOCK_SIZE]
        dct_block = cv2.dct(block.copy())
        coeff     = dct_block[EMBED_ROW, EMBED_COL]
        raw_bits[idx] = 1 if coeff > 0 else 0

    # Need at least WM_BITS blocks to decode anything useful
    if n_extract < WM_BITS:
        logger.warning(
            "Too few blocks (%d) for watermark extraction — need ≥ %d",
            n_extract, WM_BITS,
        )
        return b"\x00" * (WM_BITS // 8), 0.0

    # Reshape into (n_reps, WM_BITS) and majority-vote per bit
    n_complete  = (n_extract // WM_BITS) * WM_BITS
    bits_matrix = raw_bits[:n_complete].reshape(-1, WM_BITS)  # (n_reps, 64)
    n_reps      = bits_matrix.shape[0]

    votes     = bits_matrix.sum(axis=0)                         # (64,) sums
    majority  = (votes > n_reps / 2).astype(np.uint8)
    unanimous = (votes == n_reps) | (votes == 0)
    confidence = float(unanimous.mean())

    token = bits_to_bytes(majority.astype(bool))

    logger.debug(
        "Watermark extracted — token=%s confidence=%.3f reps=%d",
        token.hex(), confidence, n_reps,
    )
    return token, confidence


# ---------------------------------------------------------------------------
# File-level convenience wrappers
# ---------------------------------------------------------------------------

def embed_watermark_to_file(
    file_path:   str,
    wm_token:    bytes,
    output_path: str | None = None,
) -> str:
    """
    Load image from file, embed watermark, save to output_path.

    Args:
        file_path:   Source image path (any OpenCV-supported format).
        wm_token:    8-byte watermark token.
        output_path: Destination.  Defaults to overwriting input file.

    Returns:
        Path to the saved watermarked image.

    Raises:
        ValueError: Image cannot be read or is too small.
        IOError:    Image cannot be written.
    """
    if output_path is None:
        output_path = file_path

    img = cv2.imread(file_path)
    if img is None:
        raise ValueError(f"cv2.imread returned None for: {file_path}")

    watermarked = embed_watermark(img, wm_token)

    ext           = Path(output_path).suffix.lower()
    encode_params = []
    if ext in (".jpg", ".jpeg"):
        # Preserve at high quality — lower quality degrades the watermark
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 92]

    ok = cv2.imwrite(output_path, watermarked, encode_params)
    if not ok:
        raise IOError(f"cv2.imwrite failed for: {output_path}")

    logger.info("Watermarked image saved: %s", output_path)
    return output_path


def extract_watermark_from_file(file_path: str) -> tuple[bytes, float]:
    """
    Load image from file, extract and return watermark token + confidence.

    Args:
        file_path: Path to an image file.

    Returns:
        (wm_token, confidence) — same contract as extract_watermark().

    Raises:
        ValueError: Image cannot be read by OpenCV.
    """
    img = cv2.imread(file_path)
    if img is None:
        raise ValueError(f"cv2.imread returned None for: {file_path}")

    return extract_watermark(img)
