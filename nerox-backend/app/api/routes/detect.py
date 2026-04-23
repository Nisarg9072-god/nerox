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
from pathlib import Path
from typing import Annotated, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.dependencies import get_current_user
from app.core.logger import get_logger
from app.db.mongodb import get_database
from app.schemas.detect_schema import DetectionMatch, DetectionResponse
from app.services.detection_service import create_detection
from app.services.file_service import detect_file_type, validate_file
from app.services.fingerprint_service import generate_embedding_for_detection
from app.services.vector_service import get_vector_index

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
                embedding = await asyncio.to_thread(
                    generate_embedding_for_detection, str(tmp_path), file_type
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
        doc = get_database()["assets"].find_one({"_id": oid})
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

        logger.info(
            "detect (asset mode) — user=%s asset_id=%s", user_id, asset_id
        )

    # ── Search FAISS ───────────────────────────────────────────────────────────
    vector_index = get_vector_index()

    if vector_index.total == 0:
        logger.warning("detect: FAISS index is empty — no matches possible.")
        return DetectionResponse(
            query_asset_id=query_asset_id,
            total_matches=0,
            matches=[],
        )

    raw_matches = vector_index.search_similar(
        query_embedding=embedding,
        top_k=top_k,
        exclude_asset_id=exclude_id,
    )

    matches = [DetectionMatch(**m) for m in raw_matches]

    # ── Phase 6: Log each match as a detection record ─────────────────────────
    for m in raw_matches:
        match_asset_id = m.get("asset_id", "")
        match_user_id  = m.get("user_id",  user_id)
        try:
            create_detection(
                asset_id         = match_asset_id,
                user_id          = match_user_id,
                source_type      = "detect",
                similarity_score = m.get("similarity", 0.0),
                platform_name    = "unknown",
                detected_by_user = user_id,
                confidence_label = m.get("match_strength", "low"),
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
