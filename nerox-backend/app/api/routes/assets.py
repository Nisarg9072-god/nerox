"""
app/api/routes/assets.py
=========================
Asset management endpoints — Phase 2 Enterprise Upgrade.

All DB calls converted to async Motor.
BackgroundTasks replaced with production-grade TaskQueue.

Endpoints
---------
POST   /assets/upload                        — Upload, fingerprint + watermark in background
GET    /assets                               — List all assets (current user)
GET    /assets/{asset_id}                    — Single asset with full status
GET    /assets/{asset_id}/fingerprint-status — Fingerprint job details
GET    /assets/{asset_id}/watermark-status   — Watermark job details
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from bson import ObjectId
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.core.dependencies import get_current_user, get_current_user_with_role
from app.core.logger import get_logger
from app.core.rate_limiter import upload_rate_limiter
from app.db.mongodb import get_database
from app.models.asset_model import AssetStatus
from app.schemas.asset_schema import AssetItem, AssetListResponse, AssetUploadResponse
from app.schemas.fingerprint_schema import FingerprintStatusResponse
from app.schemas.watermark_schema import WatermarkStatusResponse
from app.services.file_service import (
    detect_file_type,
    generate_unique_filename,
    validate_file,
)
from app.services.fingerprint_service import create_fingerprint_record, process_fingerprint
from app.services.storage_service import get_storage
from app.services.watermark_service import create_watermark_record, process_watermark
from app.services.task_queue import task_queue
from app.services.saas_service import ROLE_ADMIN, ROLE_OWNER, enforce_upload_limit, get_organization_for_user, increment_usage

logger = get_logger(__name__)

router           = APIRouter()
ASSETS_COL       = "assets"
FINGERPRINTS_COL = "fingerprints"
WATERMARKS_COL   = "watermarks"


# ---------------------------------------------------------------------------
# Helper: MongoDB document → AssetItem schema
# ---------------------------------------------------------------------------

def _doc_to_asset_item(doc: dict) -> AssetItem:
    storage     = get_storage()
    fingerprint = doc.get("fingerprint")
    return AssetItem(
        asset_id          = str(doc["_id"]),
        filename          = doc["filename"],
        original_filename = doc["original_filename"],
        file_type         = doc["file_type"],
        file_size         = doc["file_size"],
        status            = doc["status"],
        has_fingerprint   = fingerprint is not None,
        fingerprint_dim   = len(fingerprint) if fingerprint else None,
        fingerprint_id    = doc.get("fingerprint_id"),
        watermark_id      = doc.get("watermark_id"),
        processed_at      = doc.get("processed_at"),
        created_at        = doc["created_at"],
        file_url          = doc.get("file_url") or storage.get_file_url(doc["file_path"]),
    )


# ---------------------------------------------------------------------------
# POST /assets/upload
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    response_model=AssetUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image or video asset",
    description=(
        "Upload a single image (jpg/png) or video (mp4/mov). "
        "File is validated via three-layer check (extension → MIME → magic bytes). "
        "Max size: `MAX_FILE_SIZE_MB` in `.env` (default 50 MB). "
        "Rate-limited to **10 uploads per 60 seconds** per user.\n\n"
        "**Response is returned immediately.** Two background tasks are started:\n"
        "- AI fingerprinting (ResNet50 2048-d embedding → FAISS)\n"
        "- Invisible watermarking (DCT frequency-domain token embedding)\n\n"
        "Poll status endpoints until both complete before using /detect or /watermark/verify."
    ),
)
async def upload_asset(
    current_user: Annotated[dict, Depends(get_current_user)],
    file: UploadFile = File(
        ...,
        description="Image (jpg/png) or video (mp4/mov). Max size controlled by .env.",
    ),
) -> AssetUploadResponse:
    user_id = str(current_user["_id"])
    org = await get_organization_for_user(current_user)
    org_id = str(org["_id"])
    await enforce_upload_limit(org_id, org.get("plan", "free"))

    # ── Rate limit ────────────────────────────────────────────────────────────
    if not upload_rate_limiter.is_allowed(user_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Upload rate limit exceeded. Maximum 10 uploads per minute.",
            headers={"Retry-After": "60"},
        )

    # ── Validate ──────────────────────────────────────────────────────────────
    try:
        await validate_file(file)
    except ValueError as exc:
        logger.warning("upload_validation_failed", extra={"event": "upload_validation_failed", "user_id": user_id, "filename": file.filename, "reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    # ── Save to storage ───────────────────────────────────────────────────────
    unique_filename = generate_unique_filename(file.filename or "upload")
    storage         = get_storage()

    try:
        file_path, file_size = await storage.save_file(file, unique_filename)
        file_url = storage.get_file_url(file_path)
        processing_path = storage.get_processing_path(file_path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    except IOError as exc:
        logger.exception("Storage write failed — user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file. Please try again.",
        )

    # ── Detect file type ──────────────────────────────────────────────────────
    try:
        file_type = detect_file_type(unique_filename)
    except ValueError as exc:
        storage.delete_file(file_path)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # ── Insert asset document (async) ─────────────────────────────────────────
    asset_doc = {
        "user_id":           user_id,
        "organization_id":   org_id,
        "filename":          unique_filename,
        "original_filename": file.filename or unique_filename,
        "file_type":         file_type,
        "file_path":         file_path,
        "file_size":         file_size,
        "file_url":          file_url,
        "status":            AssetStatus.PROCESSING.value,
        "fingerprint":       None,
        "fingerprint_id":    None,
        "watermark_id":      None,
        "processed_at":      None,
        "created_at":        datetime.now(timezone.utc),
    }

    db = get_database()
    try:
        result   = await db[ASSETS_COL].insert_one(asset_doc)
        asset_id = str(result.inserted_id)
    except Exception as exc:
        logger.exception("DB insert failed — user=%s: %s", user_id, exc)
        storage.delete_file(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record asset. Please try again.",
        )

    # ── Create fingerprint record (status='pending') ──────────────────────────
    fingerprint_id: str | None = None
    try:
        fingerprint_id = await create_fingerprint_record(
            asset_id=asset_id, user_id=user_id, fingerprint_type=file_type
        )
    except Exception as exc:
        logger.exception("Fingerprint record creation failed — asset=%s: %s", asset_id, exc)

    # ── Create watermark record (status='pending') ────────────────────────────
    watermark_id: str | None = None
    try:
        watermark_id = await create_watermark_record(
            asset_id=asset_id, user_id=user_id, file_type=file_type
        )
    except Exception as exc:
        logger.exception("Watermark record creation failed — asset=%s: %s", asset_id, exc)

    # ── Link both IDs back to asset document ──────────────────────────────────
    update_fields: dict = {}
    if fingerprint_id:
        update_fields["fingerprint_id"] = fingerprint_id
    if watermark_id:
        update_fields["watermark_id"] = watermark_id
    if update_fields:
        await db[ASSETS_COL].update_one({"_id": result.inserted_id}, {"$set": update_fields})

    # ── Queue background tasks (production TaskQueue) ─────────────────────────
    if fingerprint_id:
        fp_task_id = task_queue.enqueue(
            process_fingerprint,
            task_name=f"fingerprint:{asset_id}",
            max_retries=2,
            fingerprint_id=fingerprint_id,
            asset_id=asset_id,
            file_path=processing_path,
            file_type=file_type,
        )
        await db[FINGERPRINTS_COL].update_one(
            {"_id": ObjectId(fingerprint_id)},
            {"$set": {"queue_task_id": fp_task_id}},
        )
        logger.info("Fingerprint job queued: %s", asset_id)

    if watermark_id:
        wm_task_id = task_queue.enqueue(
            process_watermark,
            task_name=f"watermark:{asset_id}",
            max_retries=2,
            watermark_doc_id=watermark_id,
            asset_id=asset_id,
            user_id=user_id,
            file_path=processing_path,
            file_type=file_type,
        )
        await db[WATERMARKS_COL].update_one(
            {"_id": ObjectId(watermark_id)},
            {"$set": {"queue_task_id": wm_task_id}},
        )
        logger.info("Watermark job queued: %s", asset_id)

    logger.info(
        "Upload accepted — asset=%s fp_id=%s wm_id=%s user=%s file='%s' size=%d type=%s",
        asset_id, fingerprint_id, watermark_id, user_id, file.filename, file_size, file_type,
    )

    await increment_usage(org_id, uploads=1)
    return AssetUploadResponse(
        message=(
            "File uploaded successfully. "
            "AI fingerprinting and invisible watermarking started in background."
        ),
        asset_id=asset_id,
        fingerprint_id=fingerprint_id,
        watermark_id=watermark_id,
        filename=unique_filename,
        original_filename=file.filename or unique_filename,
        file_type=file_type,
        file_size=file_size,
        status=AssetStatus.PROCESSING.value,
        file_url=file_url,
    )


# ---------------------------------------------------------------------------
# GET /assets/{asset_id}/fingerprint-status
# MUST be declared before /{asset_id} to avoid routing conflict
# ---------------------------------------------------------------------------

@router.get(
    "/{asset_id}/fingerprint-status",
    response_model=FingerprintStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Fingerprint job status for an asset",
    description=(
        "Poll until `processing_status = completed`, then use `POST /detect` "
        "for similarity search."
    ),
)
async def get_fingerprint_status(
    asset_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> FingerprintStatusResponse:
    user_id = str(current_user["_id"])
    _require_valid_oid(asset_id)

    db    = get_database()
    await _fetch_and_own(db, ASSETS_COL, asset_id, user_id)

    fp_doc = await db[FINGERPRINTS_COL].find_one(
        {"asset_id": asset_id}, sort=[("created_at", -1)]
    )
    if fp_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No fingerprint record found for this asset.",
        )

    return FingerprintStatusResponse(
        fingerprint_id         = str(fp_doc["_id"]),
        asset_id               = asset_id,
        fingerprint_type       = fp_doc["fingerprint_type"],
        processing_status      = fp_doc["processing_status"],
        model_used             = fp_doc["model_used"],
        embedding_dim          = fp_doc.get("embedding_dim", 2048),
        frame_count            = fp_doc.get("frame_count"),
        has_embedding          = fp_doc.get("embedding_vector") is not None,
        processing_duration_ms = fp_doc.get("processing_duration_ms"),
        error_message          = fp_doc.get("error_message"),
        created_at             = fp_doc["created_at"],
        completed_at           = fp_doc.get("completed_at"),
    )


# ---------------------------------------------------------------------------
# GET /assets/{asset_id}/watermark-status
# ---------------------------------------------------------------------------

@router.get(
    "/{asset_id}/watermark-status",
    response_model=WatermarkStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Watermark job status for an asset",
    description=(
        "Poll until `status = completed`, then use `POST /watermark/verify` "
        "to verify suspicious content. "
        "Returns 403 if the asset belongs to a different user."
    ),
    responses={
        400: {"description": "Invalid asset ID"},
        403: {"description": "Asset belongs to a different user"},
        404: {"description": "Asset or watermark record not found"},
    },
)
async def get_watermark_status(
    asset_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> WatermarkStatusResponse:
    user_id = str(current_user["_id"])
    _require_valid_oid(asset_id)

    db = get_database()
    await _fetch_and_own(db, ASSETS_COL, asset_id, user_id)  # ownership + existence check

    wm_doc = await db[WATERMARKS_COL].find_one(
        {"asset_id": asset_id}, sort=[("created_at", -1)]
    )
    if wm_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No watermark record found for this asset. "
                "The asset was uploaded before Phase 5 was deployed."
            ),
        )

    v_logs = wm_doc.get("verification_logs", [])
    last_verified_at = v_logs[-1].get("verified_at") if v_logs else None

    return WatermarkStatusResponse(
        watermark_id           = str(wm_doc["_id"]),
        asset_id               = asset_id,
        file_type              = wm_doc.get("file_type", "unknown"),
        status                 = wm_doc["status"],
        watermark_method       = wm_doc["watermark_method"],
        has_token              = wm_doc.get("wm_token") is not None,
        processing_duration_ms = wm_doc.get("processing_duration_ms"),
        error_message          = wm_doc.get("error_message"),
        verification_count     = len(v_logs),
        created_at             = wm_doc["created_at"],
        completed_at           = wm_doc.get("completed_at"),
        last_verified_at       = last_verified_at,
    )


# ---------------------------------------------------------------------------
# GET /assets
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=AssetListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all assets owned by the current user",
)
async def list_assets(
    current_user: Annotated[dict, Depends(get_current_user)],
    skip:  int = Query(default=0,  ge=0,        description="Records to skip."),
    limit: int = Query(default=20, ge=1, le=100, description="Max records per page."),
) -> AssetListResponse:
    user_id = str(current_user["_id"])
    db      = get_database()
    col     = db[ASSETS_COL]

    org_id = current_user.get("organization_id")
    filt = {"organization_id": org_id} if org_id else {"user_id": user_id}
    total  = await col.count_documents(filt)
    cursor = col.find(filt).sort("created_at", -1).skip(skip).limit(limit)
    docs   = await cursor.to_list(length=limit)

    return AssetListResponse(
        total  = total,
        assets = [_doc_to_asset_item(doc) for doc in docs],
    )


# ---------------------------------------------------------------------------
# GET /assets/{asset_id}
# ---------------------------------------------------------------------------

@router.get(
    "/{asset_id}",
    response_model=AssetItem,
    status_code=status.HTTP_200_OK,
    summary="Get a single asset by ID",
    responses={
        400: {"description": "Invalid asset ID"},
        403: {"description": "Asset belongs to a different user"},
        404: {"description": "Asset not found"},
    },
)
async def get_asset(
    asset_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> AssetItem:
    user_id = str(current_user["_id"])
    _require_valid_oid(asset_id)
    db  = get_database()
    doc = await _fetch_and_own(db, ASSETS_COL, asset_id, user_id)
    return _doc_to_asset_item(doc)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _require_valid_oid(asset_id: str) -> None:
    try:
        ObjectId(asset_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{asset_id}' is not a valid asset ID.",
        )


async def _fetch_and_own(db, collection: str, asset_id: str, user_id: str) -> dict:
    doc = await db[collection].find_one({"_id": ObjectId(asset_id)})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")
    if doc["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This asset does not belong to you.",
        )
    return doc


@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete an asset (admin+)",
)
async def delete_asset(
    asset_id: str,
    current_user: Annotated[dict, Depends(get_current_user_with_role(ROLE_ADMIN, ROLE_OWNER))],
) -> dict:
    _require_valid_oid(asset_id)
    db = get_database()
    doc = await db[ASSETS_COL].find_one({"_id": ObjectId(asset_id)})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")
    if doc.get("organization_id") != current_user.get("organization_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    await db[ASSETS_COL].delete_one({"_id": ObjectId(asset_id)})
    return {"message": "Asset deleted.", "asset_id": asset_id}
