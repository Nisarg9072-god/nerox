"""
app/schemas/asset_schema.py
============================
Pydantic v2 API response schemas for asset management endpoints.
Phase 5: added watermark_id field to AssetUploadResponse and AssetItem.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Upload response  (POST /assets/upload)
# ---------------------------------------------------------------------------

class AssetUploadResponse(BaseModel):
    """Returned by POST /assets/upload on success."""

    message: str = Field(
        default=(
            "File uploaded successfully. "
            "AI fingerprinting and invisible watermarking started in background."
        ),
    )
    asset_id: str = Field(..., description="MongoDB ObjectId of the new asset.")
    fingerprint_id: Optional[str] = Field(
        default=None,
        description="Fingerprint job ObjectId — poll GET /assets/{id}/fingerprint-status.",
    )
    watermark_id: Optional[str] = Field(
        default=None,
        description="Watermark job ObjectId — poll GET /assets/{id}/watermark-status.",
    )
    filename: str = Field(..., description="UUID-based filename stored on disk.")
    original_filename: str = Field(..., description="Original filename from client.")
    file_type: str = Field(..., description="'image' or 'video'.")
    file_size: int = Field(..., description="File size in bytes.")
    status: str = Field(
        default="processing",
        description="Asset lifecycle state immediately after upload.",
    )
    file_url: Optional[str] = Field(
        default=None, description="Public URL to fetch the uploaded file."
    )


# ---------------------------------------------------------------------------
# Asset item  (GET /assets  &  GET /assets/{asset_id})
# ---------------------------------------------------------------------------

class AssetItem(BaseModel):
    """Full metadata for a single asset (list + single-fetch)."""

    asset_id: str          = Field(..., description="MongoDB ObjectId.")
    filename: str          = Field(..., description="UUID-based filename on disk.")
    original_filename: str = Field(..., description="Original filename from client.")
    file_type: str         = Field(..., description="'image' or 'video'.")
    file_size: int         = Field(..., description="File size in bytes.")
    status: str            = Field(
        ...,
        description=(
            "'processing' → tasks in progress | "
            "'completed' → fingerprint + watermark ready | "
            "'failed' → see status endpoints"
        ),
    )
    has_fingerprint: bool      = Field(default=False)
    fingerprint_dim: Optional[int]  = Field(default=None)
    fingerprint_id:  Optional[str]  = Field(
        default=None,
        description="Fingerprint job ObjectId.",
    )
    watermark_id: Optional[str] = Field(
        default=None,
        description="Watermark job ObjectId.",
    )
    processed_at: Optional[datetime] = Field(default=None)
    created_at: datetime             = Field(..., description="UTC upload timestamp.")
    file_url: Optional[str]          = Field(default=None)


# ---------------------------------------------------------------------------
# List response  (GET /assets)
# ---------------------------------------------------------------------------

class AssetListResponse(BaseModel):
    """Returned by GET /assets."""
    total:  int             = Field(..., description="Total assets for this user.")
    assets: List[AssetItem] = Field(..., description="Paginated list, newest-first.")
