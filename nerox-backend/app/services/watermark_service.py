"""
app/services/watermark_service.py
===================================
Phase 2 Enterprise Upgrade: Async record creation + sync thread-pool pipeline.

Synchronous API (async — called before HTTP response)
------------------------------------------------------
  create_watermark_record(asset_id, user_id, file_type) → watermark_doc_id
    Inserts a 'watermarks' document with status='pending'.
    Returns immediately so the client gets a watermark_id in the upload response.

Background API (sync — runs in TaskQueue thread pool)
------------------------------------------------------
  process_watermark(watermark_doc_id, asset_id, user_id, file_path, file_type)
    Steps:
      1. Mark record → 'processing'
      2. Generate cryptographically secure 8-byte wm_token (os.urandom)
      3. Embed watermark into file (overwrites original in place)
      4. Store wm_token + SHA-256 hash in DB, mark → 'completed'
      5. Link watermark_id back to the asset document
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone

from bson import ObjectId

from app.core.logger import get_logger
from app.db.mongodb import get_database, get_sync_database

logger = get_logger(__name__)

WATERMARKS_COL = "watermarks"
ASSETS_COL     = "assets"


# ---------------------------------------------------------------------------
# Async: create pending record
# ---------------------------------------------------------------------------

async def create_watermark_record(
    asset_id:  str,
    user_id:   str,
    file_type: str,
) -> str:
    """
    Insert a watermark document with status='pending' and return its ObjectId (async).
    """
    db = get_database()

    doc = {
        "asset_id":               asset_id,
        "user_id":                user_id,
        "file_type":              file_type,
        "wm_token":               None,    # 16-char hex after embedding
        "watermark_hash":         None,    # SHA-256 of wm_token bytes
        "watermark_method":       "DCT-frequency-domain",
        "status":                 "pending",
        "error_message":          None,
        "processing_duration_ms": None,
        "created_at":             datetime.now(timezone.utc),
        "updated_at":             datetime.now(timezone.utc),
        "completed_at":           None,
        "verification_logs":      [],
    }

    result = await db[WATERMARKS_COL].insert_one(doc)
    wm_id  = str(result.inserted_id)

    logger.info(
        "Watermark record created — id=%s asset=%s type=%s",
        wm_id, asset_id, file_type,
    )
    return wm_id


# ---------------------------------------------------------------------------
# Sync: full embedding pipeline (TaskQueue thread pool)
# ---------------------------------------------------------------------------

def process_watermark(
    watermark_doc_id: str,
    asset_id:         str,
    user_id:          str,
    file_path:        str,
    file_type:        str,
) -> None:
    """
    Synchronous watermark pipeline — designed to run inside TaskQueue's
    thread pool. Uses sync PyMongo client.

    Never raises to the caller unless retry is needed — all exceptions are
    caught, logged, and persisted to DB. Re-raises so TaskQueue can retry.
    """
    t_start = time.perf_counter()
    db      = get_sync_database()
    wm_oid  = ObjectId(watermark_doc_id)
    a_oid   = ObjectId(asset_id)

    # ── 1. Mark record as processing ─────────────────────────────────────────
    db[WATERMARKS_COL].update_one(
        {"_id": wm_oid},
        {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc)}},
    )

    logger.info(
        "Watermarking started — wm_id=%s asset=%s file_type=%s",
        watermark_doc_id, asset_id, file_type,
    )

    try:
        # ── 2. Generate unique, cryptographically secure token ────────────────
        wm_token:  bytes = os.urandom(8)            # 64 random bits
        wm_hash:   str   = hashlib.sha256(wm_token).hexdigest()

        # ── 3. Embed watermark into file ──────────────────────────────────────
        if file_type == "image":
            _embed_image(file_path, wm_token)
        elif file_type == "video":
            _embed_video(file_path, wm_token)
        else:
            raise ValueError(f"Unsupported file_type: '{file_type}'")

        elapsed_ms = (time.perf_counter() - t_start) * 1_000
        now        = datetime.now(timezone.utc)

        # ── 4. Persist wm_token, mark completed ──────────────────────────────
        db[WATERMARKS_COL].update_one(
            {"_id": wm_oid},
            {
                "$set": {
                    "wm_token":               wm_token.hex(),
                    "watermark_hash":         wm_hash,
                    "status":                 "completed",
                    "error_message":          None,
                    "processing_duration_ms": round(elapsed_ms, 2),
                    "updated_at":             now,
                    "completed_at":           now,
                }
            },
        )

        # ── 5. Link watermark_id back to the asset document ───────────────────
        db[ASSETS_COL].update_one(
            {"_id": a_oid},
            {"$set": {"watermark_id": watermark_doc_id}},
        )

        logger.info(
            "Watermarking complete — wm_id=%s asset=%s token=%s time=%.1fms",
            watermark_doc_id, asset_id, wm_token.hex(), elapsed_ms,
        )

    except Exception as exc:
        # ── Failure path ──────────────────────────────────────────────────────
        elapsed_ms = (time.perf_counter() - t_start) * 1_000
        error_msg  = str(exc)

        logger.exception(
            "Watermarking FAILED — wm_id=%s asset=%s: %s",
            watermark_doc_id, asset_id, exc,
        )

        try:
            db[WATERMARKS_COL].update_one(
                {"_id": wm_oid},
                {
                    "$set": {
                        "status":                 "failed",
                        "error_message":          error_msg,
                        "processing_duration_ms": round(elapsed_ms, 2),
                        "updated_at":             datetime.now(timezone.utc),
                    }
                },
            )
        except Exception as db_exc:
            logger.error(
                "Failed to persist watermark failure state for wm_id=%s: %s",
                watermark_doc_id, db_exc,
            )
        raise  # Re-raise so TaskQueue can handle retry


# ---------------------------------------------------------------------------
# Private CPU-bound helpers
# ---------------------------------------------------------------------------

def _embed_image(file_path: str, wm_token: bytes) -> None:
    """Load image, embed watermark, overwrite in place."""
    from app.services.image_watermark import embed_watermark_to_file
    embed_watermark_to_file(file_path, wm_token, output_path=file_path)


def _embed_video(file_path: str, wm_token: bytes) -> None:
    """Embed watermark into video using temp-file-then-rename strategy."""
    from app.services.video_watermark import embed_watermark_to_video
    embed_watermark_to_video(file_path, wm_token, output_path=None)
