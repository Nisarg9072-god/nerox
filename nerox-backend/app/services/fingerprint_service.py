"""
app/services/fingerprint_service.py
=====================================
Phase 2 Enterprise Upgrade: Async record creation + sync thread-pool pipeline.

High-level flow
---------------
  Async (before HTTP response):
    create_fingerprint_record(asset_id, user_id, fingerprint_type)
      → Inserts a fingerprints-collection document with status='pending'
      → Returns fingerprint_id (string)

  Background (TaskQueue, after HTTP response):
    process_fingerprint(fingerprint_id, asset_id, file_path, file_type)
      → Uses sync PyMongo (runs in thread pool via TaskQueue)
      → Updates both fingerprints and assets documents to 'processing'
      → Extracts frames via ImageProcessor or VideoProcessor
      → Generates embedding via EmbeddingService
      → Stores embedding in fingerprints document → marks 'completed'
      → Updates assets document (fingerprint, status, processed_at)
      → Appends vector to live FAISS index

  Detection (synchronous helper — used by POST /detect):
    generate_embedding_for_detection(file_path, file_type)
      → Extracts frames + generates embedding (no DB writes)
      → Returns List[float] ready for FAISS search
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List

import numpy as np
import cv2
from bson import ObjectId

from app.core.logger import get_logger
from app.db.mongodb import get_database, get_sync_database
from app.services.embedding_service import (
    EMBEDDING_DIM,
    MODEL_IDENTIFIER,
    get_embedding_service,
)
from app.services.image_processor import get_image_processor
from app.services.video_processor import get_video_processor
from app.services.ws_manager import emit_fingerprint_completed, emit_fingerprint_failed

logger = get_logger(__name__)

FINGERPRINTS_COL = "fingerprints"
ASSETS_COL       = "assets"


class FingerprintPipelineError(Exception):
    """Raised when the fingerprinting pipeline encounters a non-recoverable error."""


# ---------------------------------------------------------------------------
# Async: create pending fingerprint record before HTTP response
# ---------------------------------------------------------------------------

async def create_fingerprint_record(
    asset_id:         str,
    user_id:          str,
    fingerprint_type: str,
) -> str:
    """
    Insert a fingerprint document with status='pending' into MongoDB (async).

    Called from the upload endpoint — before the HTTP response is sent —
    so clients can immediately poll /fingerprint-status.
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

    result         = await db[FINGERPRINTS_COL].insert_one(doc)
    fingerprint_id = str(result.inserted_id)

    logger.info(
        "Fingerprint record created — id=%s asset=%s type=%s",
        fingerprint_id, asset_id, fingerprint_type,
    )
    return fingerprint_id


# ---------------------------------------------------------------------------
# Background: full pipeline (runs in TaskQueue — sync DB in thread pool)
# ---------------------------------------------------------------------------

def process_fingerprint(
    fingerprint_id: str,
    asset_id:       str,
    file_path:      str,
    file_type:      str,
) -> None:
    """
    Synchronous fingerprinting pipeline — designed to run inside TaskQueue's
    thread pool. Uses sync PyMongo client.

    Workflow:
      1. Mark fingerprint record → 'processing'
      2. Mark asset → 'processing'
      3. Extract frames (image=1, video=N keyframes)
      4. Generate embedding via EmbeddingService
      5a. Persist embedding + mark fingerprint → 'completed'
      5b. Update asset (fingerprint, status, processed_at)
      6. Append vector to live FAISS index (non-fatal)
    """
    t_start = time.perf_counter()
    db      = get_sync_database()
    fp_oid  = ObjectId(fingerprint_id)
    a_oid   = ObjectId(asset_id)
    fp_doc = db[FINGERPRINTS_COL].find_one({"_id": fp_oid}, {"user_id": 1}) or {}
    user_id = str(fp_doc.get("user_id", "")) if fp_doc.get("user_id") else ""

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
        "Fingerprint started — fingerprint_id=%s asset_id=%s type=%s",
        fingerprint_id, asset_id, file_type,
    )

    try:
        # ── Step 3: Frame extraction ──────────────────────────────────────
        frames: List[np.ndarray] = _extract_frames(file_path, file_type)
        frame_count = len(frames)
        logger.info(
            "Frame extraction complete — %d frames for asset=%s",
            frame_count, asset_id,
        )

        # ── Step 4: Embedding generation ──────────────────────────────────
        svc = get_embedding_service()
        if frame_count == 1:
            vec: np.ndarray = svc.embed_frame(frames[0])
        else:
            vec = svc.embed_frames(frames)

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
            "Fingerprint completed — id=%s asset=%s frames=%d dim=%d time=%.1fms",
            fingerprint_id, asset_id, frame_count, len(embedding_list), elapsed_ms,
        )
        if user_id:
            emit_fingerprint_completed(user_id=user_id, asset_id=asset_id, fingerprint_id=fingerprint_id)

        # ── Step 6: Update FAISS index (non-fatal) ────────────────────────
        try:
            from app.services.vector_service import get_vector_index
            get_vector_index().add_vector(asset_id, embedding_list)
            logger.info("Vector added to FAISS: %s", asset_id)
            logger.debug("FAISS index updated — asset=%s", asset_id)
        except Exception as faiss_exc:
            logger.warning(
                "FAISS update failed for asset=%s (non-fatal): %s",
                asset_id, faiss_exc,
            )

    except Exception as exc:
        # ── Failure path ──────────────────────────────────────────────────
        elapsed_ms = (time.perf_counter() - t_start) * 1_000
        error_msg  = str(exc)

        logger.exception(
            "Fingerprint failed: %s (id=%s asset=%s)",
            exc, fingerprint_id, asset_id,
        )
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
        if user_id:
            emit_fingerprint_failed(
                user_id=user_id,
                asset_id=asset_id,
                fingerprint_id=fingerprint_id,
                reason=error_msg,
            )
        raise  # Re-raise so TaskQueue can handle retry


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
    """
    frames = _extract_frames(file_path, file_type)
    svc    = get_embedding_service()

    if len(frames) == 1:
        vec = svc.embed_frame(frames[0])
    else:
        vec = svc.embed_frames(frames)

    return vec.tolist()


def generate_embeddings_for_detection_variants(
    file_path: str,
    file_type: str,
) -> list[list[float]]:
    """
    Generate multiple embeddings for a single query to improve recall on
    real-world transformations (resize/crop/blur).

    Variants (image only):
      - original (224)
      - resized from 256 → 224
      - resized from 512 → 224
      - center-crop (80%) → 224
      - slight blur → 224

    For video, falls back to the single embedding.
    """
    if file_type != "image":
        return [generate_embedding_for_detection(file_path, file_type)]

    svc = get_embedding_service()

    # Load original at native resolution (BGR)
    raw_bgr = get_image_processor().load_and_validate(file_path)

    def _to_224_rgb(bgr: np.ndarray) -> np.ndarray:
        resized = cv2.resize(bgr, (224, 224), interpolation=cv2.INTER_LANCZOS4)
        return cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

    variants_rgb: list[np.ndarray] = []

    # Variant 1: original (direct to 224)
    variants_rgb.append(_to_224_rgb(raw_bgr))

    h, w = raw_bgr.shape[:2]

    # Variant 2/3: resize the source before downscaling to model input
    for side in (256, 512):
        scale = side / float(max(h, w))
        nh = max(1, int(round(h * scale)))
        nw = max(1, int(round(w * scale)))
        bgr_scaled = cv2.resize(raw_bgr, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
        variants_rgb.append(_to_224_rgb(bgr_scaled))

    # Variant 4: center crop (80% of min side) then resize
    crop_side = int(round(min(h, w) * 0.8))
    if crop_side >= 32:
        y0 = max(0, (h - crop_side) // 2)
        x0 = max(0, (w - crop_side) // 2)
        cropped = raw_bgr[y0:y0 + crop_side, x0:x0 + crop_side]
        if cropped.size > 0:
            variants_rgb.append(_to_224_rgb(cropped))

    # Variant 5: slight blur on the native resolution, then resize
    blurred = cv2.GaussianBlur(raw_bgr, (5, 5), sigmaX=0.8)
    variants_rgb.append(_to_224_rgb(blurred))

    embeddings: list[list[float]] = []
    for rgb in variants_rgb:
        vec = svc.embed_frame(rgb)
        embeddings.append(vec.tolist())

    return embeddings


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_frames(file_path: str, file_type: str) -> List[np.ndarray]:
    """Dispatch to the correct processor based on file_type."""
    if file_type == "image":
        frame = get_image_processor().preprocess(file_path)
        return [frame]

    elif file_type == "video":
        return get_video_processor().extract_key_frames(file_path)

    else:
        raise FingerprintPipelineError(
            f"Unsupported file_type '{file_type}'. Expected 'image' or 'video'."
        )
