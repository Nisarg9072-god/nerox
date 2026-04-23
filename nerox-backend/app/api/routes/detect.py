"""
app/api/routes/detect.py
=========================
POST /detect — AI-powered content similarity detection.

Accepts either:
  • A raw file upload  — validates, generates a temporary embedding, searches the
                         FAISS index, and returns matches. The file is NOT stored.
  • An asset_id string — fetches the existing completed embedding from MongoDB,
                         searches the index, and returns matches.

At least one of 'file' or 'asset_id' must be provided; if both are supplied
the file takes precedence.

Response thresholds
-------------------
  similarity ≥ 0.90  → match_strength = "strong"
  0.70 ≤ similarity < 0.90 → match_strength = "possible"
  < 0.70  → filtered out (not returned)
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.dependencies import get_current_user
from app.core.logger import get_logger
from app.core.rate_limiter import detect_rate_limiter
from app.db.mongodb import get_database, get_sync_database
from app.schemas.detect_schema import DetectionMatch, DetectionResponse
from app.services.detection_service import create_detection
from app.services.file_service import detect_file_type, validate_file
from app.services.fingerprint_service import (
    generate_embedding_for_detection,
    generate_embeddings_for_detection_variants,
)
from app.services.vector_service import get_vector_index
from app.core.config import settings

logger = get_logger(__name__)

router = APIRouter()

# Temporary directory for detect-only file processing (files deleted after embedding)
_TEMP_DIR = Path("storage/temp")


# ---------------------------------------------------------------------------
# POST /detect
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=DetectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Detect similar content in the asset database",
    description=(
        "Upload a **file** or supply an **asset_id** to search for visually similar "
        "content across all fingerprinted assets. "
        "Uses a FAISS cosine-similarity index over 2048-d ResNet50 embeddings. "
        "Requires a valid JWT Bearer token. "
        "\n\n**Inputs (at least one required):**\n"
        "- `file` — raw image/video file; validated but **not stored permanently**.\n"
        "- `asset_id` — ObjectId of an already-processed (status=completed) asset.\n"
        "\n\n**Similarity thresholds:**\n"
        "- ≥ 0.90 → **strong** match\n"
        "- 0.70 – 0.90 → **possible** match"
    ),
    responses={
        400: {"description": "Neither file nor asset_id provided / invalid ObjectId"},
        403: {"description": "Asset does not belong to the requesting user"},
        404: {"description": "asset_id not found"},
        422: {"description": "File validation failed or asset not yet processed"},
        503: {"description": "Fingerprinting engine not available (missing dependencies)"},
    },
)
async def detect_similarity(
    current_user: Annotated[dict, Depends(get_current_user)],
    file:     Optional[UploadFile] = File(default=None,  description="Image/video to search against the database."),
    asset_id: Optional[str]        = Form(default=None,  description="ObjectId of an already-processed asset."),
    top_k:    int                  = Form(default=5, ge=1, le=20, description="Maximum number of matches to return."),
) -> DetectionResponse:
    """
    Detection flow (file mode)
    --------------------------
    1. Validate uploaded file (extension + MIME + magic bytes).
    2. Save to storage/temp/ and generate embedding via ResNet50.
    3. Delete temp file immediately after embedding.
    4. Search FAISS index for similar vectors.
    5. Return matches above threshold.

    Detection flow (asset_id mode)
    --------------------------------
    1. Validate ObjectId format.
    2. Fetch asset doc from MongoDB; enforce ownership (403 for other users).
    3. Ensure asset status == completed; return 422 if still processing.
    4. Use stored embedding directly.
    5. Search FAISS index (exclude self-match).
    6. Return matches above threshold.
    """
    user_id  = str(current_user["_id"])
    logger.info("Detection started — user=%s top_k=%d", user_id, top_k)
    if not detect_rate_limiter.is_allowed(user_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for detection requests.",
            headers={"Retry-After": "60"},
        )
    embedding: list[float]
    exclude_id: Optional[str] = None
    query_asset_id: Optional[str] = None

    # ── Input validation ───────────────────────────────────────────────────────
    if file is None and not asset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one of: 'file' (upload) or 'asset_id' (string).",
        )

    # ── Mode A: raw file upload ────────────────────────────────────────────────
    if file is not None:
        # 1. Validate
        try:
            await validate_file(file)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )

        file_type = detect_file_type(file.filename or "")
        ext       = Path(file.filename or "upload").suffix.lower()
        tmp_path  = _TEMP_DIR / f"{uuid.uuid4()}{ext}"
        _TEMP_DIR.mkdir(parents=True, exist_ok=True)

        # 2 + 3. Save temp → embed → delete
        try:
            data = await file.read()
            tmp_path.write_bytes(data)
            try:
                # Multi-variant embedding (max similarity across variants)
                embeddings = await asyncio.to_thread(
                    generate_embeddings_for_detection_variants, str(tmp_path), file_type
                )
                embedding = embeddings[0] if embeddings else []
                logger.info(
                    "Embedding(s) generated — mode=file user=%s variants=%d",
                    user_id, len(embeddings),
                )
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=str(exc),
                )
        finally:
            tmp_path.unlink(missing_ok=True)

        logger.info(
            "detect (file mode) — user=%s file='%s' type=%s",
            user_id, file.filename, file_type,
        )

    # ── Mode B: query by existing asset_id ────────────────────────────────────
    else:
        # 1. Validate ObjectId
        try:
            oid = ObjectId(asset_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{asset_id}' is not a valid asset ID.",
            )

        # 2. Fetch doc + ownership check
        doc = await get_database()["assets"].find_one({"_id": oid})
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found.",
            )
        if doc["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. This asset does not belong to you.",
            )

        # 3. Ensure fingerprint is ready
        if doc.get("status") != "completed" or not doc.get("fingerprint"):
            current_status = doc.get("status", "unknown")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Asset '{asset_id}' is not yet fingerprinted "
                    f"(current status: {current_status}). "
                    "Wait for status='completed' and retry."
                ),
            )

        embedding       = doc["fingerprint"]
        exclude_id      = asset_id
        query_asset_id  = asset_id
        logger.info("Embedding generated — mode=asset user=%s asset_id=%s", user_id, asset_id)

        logger.info(
            "detect (asset mode) — user=%s asset_id=%s", user_id, asset_id
        )

    # ── Search FAISS ───────────────────────────────────────────────────────────
    vector_index = get_vector_index()
    # Keep API-process FAISS in sync with worker-completed fingerprints.
    vector_index.load_from_db()

    if vector_index.total == 0:
        logger.warning("detect: FAISS index is empty — no matches possible.")
        return DetectionResponse(
            query_asset_id=query_asset_id,
            total_matches=0,
            matches=[],
        )

    include_below = bool(settings.DEBUG_DETECTION)
    min_floor = float(settings.DETECT_SIMILARITY_MIN)

    if file is not None:
        # file-mode uses multi embeddings if available
        try:
            embeddings  # type: ignore[name-defined]
        except Exception:
            embeddings = [embedding]
        raw_matches = vector_index.search_similar_multi(
            query_embeddings=embeddings,
            top_k=top_k,
            exclude_asset_id=exclude_id,
            min_similarity=min_floor,
            include_below_threshold=include_below,
        )
    else:
        raw_matches = vector_index.search_similar(
            query_embedding=embedding,
            top_k=top_k,
            exclude_asset_id=exclude_id,
            min_similarity=min_floor,
            include_below_threshold=include_below,
        )
    if raw_matches:
        match_ids = [ObjectId(m["asset_id"]) for m in raw_matches if ObjectId.is_valid(m.get("asset_id", ""))]
        if match_ids:
            asset_docs = await get_database()["assets"].find(
                {"_id": {"$in": match_ids}},
                {"_id": 1, "user_id": 1, "filename": 1},
            ).to_list(length=len(match_ids))
            by_id = {str(d["_id"]): d for d in asset_docs}
            for m in raw_matches:
                doc = by_id.get(m.get("asset_id", ""))
                if doc:
                    m["user_id"] = doc.get("user_id")
                    m["filename"] = doc.get("filename")
    if raw_matches:
        logger.info(
            "Similarity computed — top match score: %.4f",
            float(raw_matches[0].get("similarity", 0.0)),
        )
        logger.info(
            "detect: similarity distribution (top %d) — %s",
            min(len(raw_matches), 5),
            [float(m.get("similarity", 0.0)) for m in raw_matches[:5]],
        )
    else:
        logger.info("Similarity computed — no matches above threshold")

    matches = [DetectionMatch(**m) for m in raw_matches]

    # ── Phase 6: Log each match as a detection record ─────────────────────────
    for m in raw_matches:
        match_asset_id = m.get("asset_id", "")
        match_user_id  = m.get("user_id",  user_id)
        owner_asset_id = query_asset_id or match_asset_id
        try:
            create_detection(
                asset_id         = owner_asset_id,
                matched_asset_id = match_asset_id,
                user_id          = match_user_id,
                source_type      = "detect",
                similarity_score = m.get("similarity", 0.0),
                platform_name    = m.get("platform_name", "unknown"),
                detected_by_user = user_id,
                confidence_label = m.get("confidence", m.get("match_strength", "low")),
            )
        except Exception as exc:
            logger.warning(
                "Failed to log detection for asset=%s: %s", match_asset_id, exc
            )

    logger.info(
        "detect: found %d matches (top_k=%d) for user=%s",
        len(matches), top_k, user_id,
    )

    return DetectionResponse(
        query_asset_id=query_asset_id,
        total_matches=len(matches),
        matches=matches,
    )


# ===========================================================================
# Phase 2.5: Auto-Detection Endpoints
# ===========================================================================

from app.schemas.auto_detect_schema import (
    StartAutoDetectRequest,
    StartAutoDetectResponse,
    DetectionJobItem,
    DetectionJobListResponse,
    DetectionJobDetailResponse,
    DetectionJobMatchResult,
)
from app.services.auto_detect_service import create_detection_job, run_detection_job
from app.services.task_queue import task_queue
from app.models.detection_job_model import DETECTION_JOBS_COL
from app.core.config import settings


def _job_doc_to_item(doc: dict) -> DetectionJobItem:
    """Convert a raw MongoDB detection_job document to the API schema."""
    return DetectionJobItem(
        job_id=str(doc["_id"]),
        status=doc.get("status", "unknown"),
        source=doc.get("source", ""),
        query=doc.get("query", ""),
        total_scanned=doc.get("total_scanned", 0),
        matches_found=doc.get("matches_found", 0),
        started_at=doc["started_at"].isoformat() if doc.get("started_at") else None,
        completed_at=doc["completed_at"].isoformat() if doc.get("completed_at") else None,
        error=doc.get("error"),
        created_at=doc["created_at"].isoformat() if doc.get("created_at") else "",
    )


# ---------------------------------------------------------------------------
# POST /detect/auto/start
# ---------------------------------------------------------------------------

@router.post(
    "/auto/start",
    response_model=StartAutoDetectResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start an automated detection job",
    description=(
        "Triggers a background detection job that scans external sources "
        "(YouTube, web) for content similar to the user's protected assets. "
        "The job runs asynchronously — poll `GET /detect/jobs/{id}` for progress."
    ),
)
async def start_auto_detection(
    body: StartAutoDetectRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> StartAutoDetectResponse:
    """
    Create and dispatch an auto-detection job.

    1. Validate the source type.
    2. Create a job document in MongoDB (status=pending).
    3. Dispatch to the TaskQueue for background execution.
    4. Return the job_id immediately.
    """
    user_id = str(current_user["_id"])

    # Validate source
    valid_sources = {"youtube", "web"}
    if body.source not in valid_sources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source '{body.source}'. Must be one of: {', '.join(valid_sources)}",
        )

    # Create job
    job_id = await create_detection_job(
        user_id=user_id,
        source=body.source,
        query=body.query,
        asset_ids=body.asset_ids,
    )

    # Dispatch to background worker
    task_id = task_queue.enqueue(
        run_detection_job,
        job_id=job_id,
        task_name=f"auto_detect_{job_id[:8]}",
        max_retries=2,
        timeout_sec=float(settings.AUTO_SCAN_TIMEOUT_SEC),
    )
    await get_database()[DETECTION_JOBS_COL].update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {
            "queue_task_id": task_id,
            "status": "pending",
            "retries": 0,
            "max_retries": 2,
            "queued_at": datetime.now(timezone.utc),
        }},
    )

    logger.info(
        "Auto-detection job dispatched — job_id=%s task_id=%s queue=%s source=%s user=%s",
        job_id, task_id, settings.RQ_QUEUE_NAME, body.source, user_id,
    )

    return StartAutoDetectResponse(
        job_id=job_id,
        status="pending",
        message=f"Detection job created. Scanning {body.source} for: '{body.query}'",
    )


# ---------------------------------------------------------------------------
# GET /detect/jobs
# ---------------------------------------------------------------------------

@router.get(
    "/jobs",
    response_model=DetectionJobListResponse,
    summary="List detection jobs",
    description="Returns all detection jobs for the authenticated user, sorted by creation date (newest first).",
)
async def list_detection_jobs(
    current_user: Annotated[dict, Depends(get_current_user)],
    limit: int = 20,
    skip: int = 0,
) -> DetectionJobListResponse:
    """List detection jobs for the current user."""
    user_id = str(current_user["_id"])
    db = get_database()

    total = await db[DETECTION_JOBS_COL].count_documents({"user_id": user_id})

    cursor = (
        db[DETECTION_JOBS_COL]
        .find({"user_id": user_id})
        .sort("created_at", -1)
        .skip(skip)
        .limit(min(limit, 50))
    )

    jobs = []
    async for doc in cursor:
        jobs.append(_job_doc_to_item(doc))

    return DetectionJobListResponse(total=total, jobs=jobs)


# ---------------------------------------------------------------------------
# GET /detect/jobs/{job_id}
# ---------------------------------------------------------------------------

@router.get(
    "/jobs/{job_id}",
    response_model=DetectionJobDetailResponse,
    summary="Get detection job details",
    description="Returns full details of a specific detection job, including match results.",
    responses={
        404: {"description": "Job not found."},
        403: {"description": "Job belongs to another user."},
    },
)
async def get_detection_job(
    job_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> DetectionJobDetailResponse:
    """Get detailed information about a specific detection job."""
    user_id = str(current_user["_id"])

    try:
        oid = ObjectId(job_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{job_id}' is not a valid job ID.",
        )

    db = get_database()
    doc = await db[DETECTION_JOBS_COL].find_one({"_id": oid})

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Detection job not found.",
        )

    if doc["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This job belongs to another user.",
        )

    # Convert results to schema
    results = [
        DetectionJobMatchResult(**r)
        for r in doc.get("results", [])
    ]

    return DetectionJobDetailResponse(
        job_id=str(doc["_id"]),
        status=doc.get("status", "unknown"),
        source=doc.get("source", ""),
        query=doc.get("query", ""),
        total_scanned=doc.get("total_scanned", 0),
        matches_found=doc.get("matches_found", 0),
        results=results,
        started_at=doc["started_at"].isoformat() if doc.get("started_at") else None,
        completed_at=doc["completed_at"].isoformat() if doc.get("completed_at") else None,
        error=doc.get("error"),
        created_at=doc["created_at"].isoformat() if doc.get("created_at") else "",
    )
