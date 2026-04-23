"""
app/api/routes/watermark.py
============================
Phase 5 watermark API endpoints.

POST /watermark/verify
    Accept any suspicious image or video, extract the invisible DCT watermark,
    compare against the Nerox ownership database, and return a full trace report.

GET /watermark/health
    Lightweight diagnostic: shows total watermarks indexed in MongoDB.

The GET /assets/{asset_id}/watermark-status endpoint lives in assets.py
because it is scoped to a specific asset and fits the /assets prefix.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.dependencies import get_current_user
from app.core.logger import get_logger
from app.db.mongodb import get_database
from app.schemas.watermark_schema import OwnershipMatch, VerifyResponse
from app.services.detection_service import create_detection
from app.services.file_service import detect_file_type, validate_file
from app.services.watermark_verify import verify_file

logger  = get_logger(__name__)
router  = APIRouter()
_TMPDIR = Path("storage/temp")

WATERMARKS_COL = "watermarks"


# ---------------------------------------------------------------------------
# POST /watermark/verify
# ---------------------------------------------------------------------------

@router.post(
    "/verify",
    response_model=VerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify ownership of a suspicious file via invisible watermark extraction",
    description=(
        "Upload a suspicious image or video to trace its original owner using "
        "the invisible DCT frequency-domain watermark embedded at upload time.\n\n"
        "**How it works:**\n"
        "1. The system extracts the hidden 8-byte watermark token from the file.\n"
        "2. The token is looked up in the Nerox ownership database.\n"
        "3. If found, the original `asset_id` and `user_id` are returned.\n\n"
        "**Confidence labels:**\n"
        "- `strong` (≥ 0.85)     — watermark clearly intact\n"
        "- `probable` (0.60–0.85) — minor compression/resize degradation\n"
        "- `possible` (0.40–0.60) — heavy editing; token may still be correct\n"
        "- `insufficient` (< 0.40) — watermark severely damaged\n\n"
        "**The uploaded file is NEVER stored** — it is deleted immediately "
        "after watermark extraction. Requires a valid JWT Bearer token.\n\n"
        "Supported formats: jpg, png, mp4, mov."
    ),
    responses={
        200: {"description": "Extraction succeeded (verified=True or verified=False)"},
        422: {"description": "File validation failed"},
        500: {"description": "Internal extraction error"},
    },
)
async def verify_watermark(
    current_user: Annotated[dict, Depends(get_current_user)],
    file: UploadFile = File(
        ...,
        description="Suspicious image (jpg/png) or video (mp4/mov) to verify.",
    ),
) -> VerifyResponse:
    """
    Verification flow
    -----------------
    1. Validate file (extension + MIME + magic bytes).
    2. Save to storage/temp/ (non-persistent).
    3. Run DCT extraction + DB lookup (in thread pool, CPU-bound).
    4. Delete temp file regardless of outcome.
    5. Append audit log entry if verified.
    6. Return VerifyResponse.
    """
    user_id = str(current_user["_id"])

    # ── 1. Validate ───────────────────────────────────────────────────────────
    try:
        await validate_file(file)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    file_type = detect_file_type(file.filename or "")
    ext       = Path(file.filename or "verify").suffix.lower()
    tmp_path  = _TMPDIR / f"verify_{uuid.uuid4()}{ext}"
    _TMPDIR.mkdir(parents=True, exist_ok=True)

    # ── 2 + 3. Save → extract → delete ───────────────────────────────────────
    try:
        data = await file.read()
        tmp_path.write_bytes(data)

        result = await asyncio.to_thread(verify_file, str(tmp_path), file_type)

    except Exception as exc:
        logger.exception(
            "Unhandled error during watermark verification — user=%s: %s", user_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification failed due to an internal error. Please try again.",
        )
    finally:
        tmp_path.unlink(missing_ok=True)   # always delete temp file

    # ── 4. Build ownership sub-object ──────────────────────────────────────────
    ownership: Optional[OwnershipMatch] = None
    if result.verified and result.asset_id:
        ownership = OwnershipMatch(
            asset_id     = result.asset_id,
            user_id      = result.user_id or "",
            watermark_id = result.watermark_id_db or "",
        )
        # Append audit entry (non-fatal)
        try:
            db = get_database()
            await db[WATERMARKS_COL].update_one(
                {"wm_token": result.wm_token_hex},
                {
                    "$push": {
                        "verification_logs": {
                            "verified_by_user": user_id,
                            "confidence":       round(result.confidence, 4),
                            "verified_at":      datetime.now(timezone.utc).isoformat(),
                        }
                    }
                },
            )
        except Exception:
            pass

        # ── Phase 6: Log as a detection record ────────────────────────────────
        try:
            create_detection(
                asset_id           = result.asset_id,
                user_id            = result.user_id or user_id,
                source_type        = "watermark",
                similarity_score   = result.confidence,
                platform_name      = "unknown",
                watermark_verified = True,
                detected_by_user   = user_id,
                confidence_label   = result.confidence_label,
                notes              = "Verified via POST /watermark/verify",
            )
        except Exception as exc:
            logger.warning("Could not log watermark detection: %s", exc)

    logger.info(
        "Watermark verify — user=%s file='%s' verified=%s confidence=%.3f token=%s",
        user_id, file.filename, result.verified, result.confidence, result.wm_token_hex,
    )

    return VerifyResponse(
        verified          = result.verified,
        confidence        = round(result.confidence, 4),
        confidence_label  = result.confidence_label,
        ownership         = ownership,
        wm_token_detected = result.wm_token_hex,
        watermark_method  = result.method,
        error             = result.error,
    )


# ---------------------------------------------------------------------------
# GET /watermark/health
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    tags=["Health"],
    summary="Watermark sub-system health",
    description="Returns statistics about the watermarks collection.",
)
async def watermark_health(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    db = get_database()

    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]
    counts = {}
    async for doc in db[WATERMARKS_COL].aggregate(pipeline):
        counts[doc["_id"]] = doc["count"]

    return {
        "service":   "nerox-watermark",
        "method":    "DCT-frequency-domain",
        "version":   "5.0.0",
        "pending":   counts.get("pending",    0),
        "processing": counts.get("processing", 0),
        "completed": counts.get("completed",  0),
        "failed":    counts.get("failed",     0),
        "total":     sum(counts.values()),
    }
