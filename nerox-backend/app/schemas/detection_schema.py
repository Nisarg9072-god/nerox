"""
app/schemas/detection_schema.py
==================================
Pydantic v2 API schemas for detection records.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class DetectionCreate(BaseModel):
    """
    Request body for POST /analytics/manual-detection.
    Allows admin/demo insertion of detection events.
    """
    asset_id:         str   = Field(..., description="Asset ObjectId to log a detection against.")
    platform_name:    str   = Field(
        default="unknown",
        description="Platform where the content was found (instagram, youtube, website, etc.).",
    )
    source_url:       Optional[str]   = Field(default=None, description="URL of the infringing content.")
    similarity_score: float = Field(
        default=0.80, ge=0.0, le=1.0, description="Match confidence [0, 1]."
    )
    confidence_label: str   = Field(
        default="strong",
        description="strong | medium | low",
    )
    watermark_verified: bool = Field(
        default=False, description="True if watermark extraction confirmed ownership."
    )
    notes:            Optional[str]   = Field(default=None, description="Optional notes.")


class DetectionItem(BaseModel):
    """Single detection record returned in API responses."""

    detection_id:        str      = Field(..., description="MongoDB ObjectId of this detection.")
    asset_id:            str
    user_id:             str
    source_type:         str
    platform_name:       str
    source_url:          Optional[str]  = None
    similarity_score:    float
    confidence_label:    str
    risk_score:          int
    risk_label:          str
    watermark_verified:  bool
    verification_status: str
    notes:               Optional[str]  = None
    detected_at:         datetime
    created_at:          datetime


class DetectionListResponse(BaseModel):
    """Returned by list-style detection endpoints."""
    total:      int
    detections: List[DetectionItem]
