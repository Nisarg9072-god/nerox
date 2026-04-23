"""
app/services/fingerprint_service.py
=====================================
Orchestration layer for the Phase 4 AI fingerprinting pipeline.

High-level flow
---------------
  Synchronous (before HTTP response):
    create_fingerprint_record(asset_id, user_id, fingerprint_type)
      → Inserts a fingerprints-collection document with status='pending'
      → Returns fingerprint_id (string)

  Asynchronous (BackgroundTask, after HTTP response):
    process_fingerprint(fingerprint_id, asset_id, file_path, file_type)
      → Updates both fingerprints and assets documents to 'processing'
      → Extracts frames via ImageProcessor or VideoProcessor
      → Generates embedding via EmbeddingService (thread-pool)
      → Stores embedding in fingerprints document → marks 'completed'
      → Updates assets document (fingerprint, status, processed_at)
      → Appends vector to live FAISS index

  Detection (synchronous helper — used by POST /detect):
    generate_embedding_for_detection(file_path, file_type)
      → Extracts frames + generates embedding (no DB writes)
      → Returns List[float] ready for FAISS search

Error handling
--------------
  Any exception during process_fingerprint:
    - fingerprints.processing_status  → 'failed'
    - fingerprints.error_message      → str(exc)
    - assets.status                   → 'failed'
    - No crash, no silent swallo — always logged at ERROR level.

Import safety
-------------
  audio/video/torch imports happen lazily inside the functions that need them.
  Module-level imports are limited to stdlib + app.core to prevent circular deps.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import List

import numpy as np
from bson import ObjectId

from app.core.logger import get_logger
from app.db.mongodb import get_database
from app.services.embedding_service import (
    EMBEDDING_DIM,
    MODEL_IDENTIFIER,
    get_embedding_service,
)
from app.services.image_processor import get_image_processor
from app.services.video_processor import get_video_processor

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Collection names
# ---------------------------------------------------------------------------

FINGERPRINTS_COL = "fingerprints"
ASSETS_COL       = "assets"


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class FingerprintPipelineError(Exception):
    """Raised when the fingerprinting pipeline encounters a non-recoverable error."""


# ---------------------------------------------------------------------------
# Synchronous: create pending fingerprint record before HTTP response
# ---------------------------------------------------------------------------

def create_fingerprint_record(
    asset_id:         str,
    user_id:          str,
    fingerprint_type: str,
) -> str:
    """
    Insert a fingerprint document with status='pending' into MongoDB.

    Called synchronously inside the upload endpoint — before the HTTP response
    is sent — so clients can immediately poll /fingerprint-status.

    Args:
        asset_id:         MongoDB ObjectId string of the parent asset.
        user_id:          MongoDB ObjectId string of the owning user.
        fingerprint_type: 'image' | 'video'

    Returns:
        fingerprint_id as a string (MongoDB ObjectId).

    Raises:
        Any PyMongo exception propagates to the upload endpoint for 500 handling.
    """
    db = get_database()

    doc = {
        "asset_id":               asset_id,
        "user_id":                user_id,
        "fingerprint_type":       fingerprint_type,
        "embedding_vector":       None,
        "embedding_dim":          EMBEDDING_DIM,
        "model_used":             MODEL_IDENTIFIER,
        "frame_count":            None,
        "processing_status":      "pending",
        "error_message":          None,
        "created_at":             datetime.now(timezone.utc),
        "completed_at":           None,
        "processing_duration_ms": None,
    }

    result         = db[FINGERPRINTS_COL].insert_one(doc)
    fingerprint_id = str(result.inserted_id)

    logger.info(
        "Fingerprint record created — id=%s asset=%s type=%s",
        fingerprint_id, asset_id, fingerprint_type,
    )
    return fingerprint_id


# ---------------------------------------------------------------------------
# Asynchronous: full pipeline (runs in BackgroundTask after HTTP response)
# ---------------------------------------------------------------------------

async def process_fingerprint(
    fingerprint_id: str,
    asset_id:       str,
    file_path:      str,
    file_type:      str,
) -> None:
    """
    Background coroutine: execute the full AI fingerprinting pipeline.

    Workflow:
      1.  Mark fingerprint record → 'processing'
      2.  Mark asset → 'processing'
      3.  Extract frames (image=1 frame, video=N keyframes) in thread pool
      4.  Generate embedding via EmbeddingService in thread pool
      5a. Persist embedding + mark fingerprint → 'completed'
      5b. Update asset (fingerprint, status, processed_at, fingerprint_id)
      6.  Append vector to live FAISS index (non-fatal if fails)

    On any exception:
      - fingerprints.processing_status → 'failed'
      - fingerprints.error_message     → error string
      - assets.status                  → 'failed'

    Args:
        fingerprint_id: MongoDB ObjectId string of the fingerprint record.
        asset_id:       MongoDB ObjectId string of the parent asset.
        file_path:      Absolute path to the stored file on disk.
        file_type:      'image' | 'video'
    """
    t_start = time.perf_counter()
    db      = get_database()
    fp_oid  = ObjectId(fingerprint_id)
    a_oid   = ObjectId(asset_id)

    # ── Step 1 + 2: Mark both records as 'processing' ──────────────────────
    db[FINGERPRINTS_COL].update_one(
        {"_id": fp_oid},
        {"$set": {"processing_status": "processing"}},
    )
    db[ASSETS_COL].update_one(
        {"_id": a_oid},
        {"$set": {"status": "processing"}},
    )

    logger.info(
        "Fingerprinting started — fingerprint_id=%s asset_id=%s type=%s",
        fingerprint_id, asset_id, file_type,
    )

    try:
        # ── Step 3: Frame extraction (CPU-bound → thread pool) ────────────
        frames: List[np.ndarray] = await asyncio.to_thread(
            _extract_frames, file_path, file_type
        )
        frame_count = len(frames)
        logger.info(
            "Frame extraction complete — %d frames for asset=%s",
            frame_count, asset_id,
        )

        # ── Step 4: Embedding generation (CPU-bound → thread pool) ────────
        svc = get_embedding_service()
        if frame_count == 1:
            vec: np.ndarray = await asyncio.to_thread(svc.embed_frame, frames[0])
        else:
            vec = await asyncio.to_thread(svc.embed_frames, frames)

        embedding_list = vec.tolist()
        elapsed_ms     = (time.perf_counter() - t_start) * 1_000
        now            = datetime.now(timezone.utc)

        # ── Step 5a: Persist embedding, mark fingerprint 'completed' ──────
        db[FINGERPRINTS_COL].update_one(
            {"_id": fp_oid},
            {
                "$set": {
                    "embedding_vector":       embedding_list,
                    "frame_count":            frame_count,
                    "processing_status":      "completed",
                    "completed_at":           now,
                    "processing_duration_ms": round(elapsed_ms, 2),
                    "error_message":          None,
                }
            },
        )

        # ── Step 5b: Update asset document ───────────────────────────────
        db[ASSETS_COL].update_one(
            {"_id": a_oid},
            {
                "$set": {
                    "fingerprint":    embedding_list,
                    "fingerprint_id": fingerprint_id,
                    "status":         "completed",
                    "processed_at":   now,
                }
            },
        )

        logger.info(
            "Fingerprinting complete — id=%s asset=%s frames=%d dim=%d time=%.1fms",
            fingerprint_id, asset_id, frame_count, len(embedding_list), elapsed_ms,
        )

        # ── Step 6: Update FAISS index (non-fatal) ────────────────────────
        try:
            from app.services.vector_service import get_vector_index
            get_vector_index().add_vector(asset_id, embedding_list)
            logger.debug("FAISS index updated — asset=%s", asset_id)
        except Exception as faiss_exc:
            # FAISS update failure is non-fatal; index rebuilds from DB on restart
            logger.warning(
                "FAISS update failed for asset=%s (non-fatal): %s",
                asset_id, faiss_exc,
            )

    except Exception as exc:
        # ── Failure path ──────────────────────────────────────────────────
        elapsed_ms = (time.perf_counter() - t_start) * 1_000
        error_msg  = str(exc)

        logger.exception(
            "Fingerprinting FAILED — id=%s asset=%s: %s",
            fingerprint_id, asset_id, exc,
        )

        try:
            db[FINGERPRINTS_COL].update_one(
                {"_id": fp_oid},
                {
                    "$set": {
                        "processing_status":      "failed",
                        "error_message":          error_msg,
                        "processing_duration_ms": round(elapsed_ms, 2),
                    }
                },
            )
            db[ASSETS_COL].update_one(
                {"_id": a_oid},
                {"$set": {"status": "failed"}},
            )
        except Exception as db_exc:
            logger.error(
                "Failed to persist failure state for fingerprint_id=%s: %s",
                fingerprint_id, db_exc,
            )


# ---------------------------------------------------------------------------
# Detection helper (no DB writes — used by POST /detect)
# ---------------------------------------------------------------------------

def generate_embedding_for_detection(
    file_path: str,
    file_type: str,
) -> List[float]:
    """
    Generate an embedding for on-the-fly detection (no persistence).

    Used by POST /detect when a raw file is uploaded for similarity search.
    The file is a temporary file that the caller is responsible for deleting.

    Args:
        file_path: Absolute path to the temporary file on disk.
        file_type: 'image' | 'video'

    Returns:
        2048-d embedding as a Python list of floats.

    Raises:
        ValueError:   On unreadable file or unsupported file_type.
        RuntimeError: If torch/torchvision are not installed.
    """
    frames = _extract_frames(file_path, file_type)
    svc    = get_embedding_service()

    if len(frames) == 1:
        vec = svc.embed_frame(frames[0])
    else:
        vec = svc.embed_frames(frames)

    return vec.tolist()


# ---------------------------------------------------------------------------
# Private helpers — run in thread pool via asyncio.to_thread
# ---------------------------------------------------------------------------

def _extract_frames(file_path: str, file_type: str) -> List[np.ndarray]:
    """
    Dispatch to the correct processor based on file_type.

    Args:
        file_path: Path to the file on disk.
        file_type: 'image' | 'video'

    Returns:
        List of (224, 224, 3) RGB uint8 numpy arrays.

    Raises:
        FingerprintPipelineError: On unknown file_type.
        ValueError: On unreadable / empty file.
    """
    if file_type == "image":
        frame = get_image_processor().preprocess(file_path)
        return [frame]

    elif file_type == "video":
        return get_video_processor().extract_key_frames(file_path)

    else:
        raise FingerprintPipelineError(
            f"Unsupported file_type '{file_type}'. Expected 'image' or 'video'."
        )
