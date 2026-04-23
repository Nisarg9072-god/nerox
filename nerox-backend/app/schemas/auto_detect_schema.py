"""
app/schemas/auto_detect_schema.py
====================================
Pydantic v2 schemas for Phase 2.5 Auto-Detection API endpoints.

Endpoints:
  POST /detect/auto/start  → StartAutoDetectRequest → StartAutoDetectResponse
  GET  /detect/jobs        → DetectionJobListResponse
  GET  /detect/jobs/{id}   → DetectionJobDetailResponse
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# POST /detect/auto/start
# ---------------------------------------------------------------------------

class StartAutoDetectRequest(BaseModel):
    """Request body to manually trigger an auto-detection job."""

    source: str = Field(
        default="youtube",
        description="Ingestion source: 'youtube' | 'web'",
    )
    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Search keyword (YouTube) or URL (web scraper).",
    )
    asset_ids: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional list of specific asset IDs to compare against. "
            "If omitted, all user's completed assets are used."
        ),
    )


class StartAutoDetectResponse(BaseModel):
    """Response after starting a detection job."""

    job_id:  str = Field(..., description="MongoDB ObjectId of the new detection job.")
    status:  str = Field(default="pending", description="Initial job status.")
    message: str = Field(default="Detection job created successfully.")


# ---------------------------------------------------------------------------
# GET /detect/jobs  and  GET /detect/jobs/{id}
# ---------------------------------------------------------------------------

class DetectionJobMatchResult(BaseModel):
    """A single match result within a detection job."""

    asset_id:       str   = Field(..., description="Matched asset ObjectId.")
    asset_filename: str   = Field(default="", description="Original asset filename.")
    similarity:     float = Field(..., description="Cosine similarity score.")
    match_strength: str   = Field(..., description="'strong' or 'possible'.")
    source_url:     str   = Field(default="", description="URL of the detected content.")
    source_title:   str   = Field(default="", description="Title of the detected content.")
    platform:       str   = Field(default="unknown", description="Platform name.")
    detected_at:    str   = Field(default="", description="ISO timestamp of detection.")


class DetectionJobItem(BaseModel):
    """Summary of a detection job (for list view)."""

    job_id:        str            = Field(..., description="MongoDB ObjectId.")
    status:        str            = Field(..., description="pending | running | completed | failed")
    source:        str            = Field(..., description="youtube | web | upload | api")
    query:         str            = Field(..., description="Search query or URL.")
    total_scanned: int            = Field(default=0)
    matches_found: int            = Field(default=0)
    started_at:    Optional[str]  = None
    completed_at:  Optional[str]  = None
    error:         Optional[str]  = None
    created_at:    str            = Field(..., description="ISO timestamp.")


class DetectionJobListResponse(BaseModel):
    """Paginated list of detection jobs."""

    total: int
    jobs:  List[DetectionJobItem]


class DetectionJobDetailResponse(BaseModel):
    """Full details of a single detection job, including results."""

    job_id:        str            = Field(..., description="MongoDB ObjectId.")
    status:        str
    source:        str
    query:         str
    total_scanned: int            = 0
    matches_found: int            = 0
    results:       List[DetectionJobMatchResult] = Field(default_factory=list)
    started_at:    Optional[str]  = None
    completed_at:  Optional[str]  = None
    error:         Optional[str]  = None
    created_at:    str
