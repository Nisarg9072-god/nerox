"""
app/models/watermark_model.py
================================
Database-layer model for documents in MongoDB's 'watermarks' collection.

Collection: watermarks
Indexes (created at startup by main.py):
  - asset_id               → O(1) lookup by asset
  - user_id                → per-user queries
  - wm_token               → unique lookup during verification
  - status                 → monitoring / admin queries
  - (asset_id, created_at) → sorted latest-record retrieval
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class WatermarkStatus(str, Enum):
    """Lifecycle state machine for a watermark record."""
    PENDING    = "pending"      # Record created; background task not yet started
    PROCESSING = "processing"   # Embedding actively in progress
    COMPLETED  = "completed"    # Token embedded and stored; ready for verification
    FAILED     = "failed"       # Embedding failed (see error_message)


class WatermarkModel(BaseModel):
    """
    Represents a single Watermark document in MongoDB.

    Fields
    ------
    asset_id               : str              Parent asset ObjectId string.
    user_id                : str              Owner user ObjectId string.
    file_type              : str              'image' | 'video'
    wm_token               : Optional[str]    16-char hex of 8-byte random token.
    watermark_hash         : Optional[str]    SHA-256 hex of the wm_token bytes.
    watermark_method       : str              Algorithm identifier.
    status                 : WatermarkStatus  Lifecycle state.
    error_message          : Optional[str]    Set on failure.
    processing_duration_ms : Optional[float]  Wall-clock time in ms.
    created_at             : datetime         UTC creation timestamp.
    updated_at             : datetime         UTC last-update timestamp.
    completed_at           : Optional[datetime] UTC completion timestamp.
    verification_logs      : List[dict]       Audit trail of verifications.
    """

    asset_id:               str = Field(
        ..., description="ObjectId string of the parent asset."
    )
    user_id:                str = Field(
        ..., description="ObjectId string of the owning user."
    )
    file_type:              str = Field(
        ..., description="'image' or 'video'."
    )
    wm_token:               Optional[str] = Field(
        default=None,
        description="16-char hex string (8-byte random token embedded in the file).",
    )
    watermark_hash:         Optional[str] = Field(
        default=None,
        description="SHA-256 hex of the wm_token bytes — for integrity verification.",
    )
    watermark_method:       str = Field(
        default="DCT-frequency-domain",
        description="Watermarking algorithm identifier.",
    )
    status:                 WatermarkStatus = Field(
        default=WatermarkStatus.PENDING,
        description="Current lifecycle state.",
    )
    error_message:          Optional[str] = Field(
        default=None,
        description="Human-readable failure description (status='failed' only).",
    )
    processing_duration_ms: Optional[float] = Field(
        default=None,
        description="Total wall-clock embedding time in milliseconds.",
    )
    created_at:             datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this record was created.",
    )
    updated_at:             datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the last status update.",
    )
    completed_at:           Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when embedding completed or failed.",
    )
    verification_logs:      List[Dict] = Field(
        default_factory=list,
        description="Appended each time POST /watermark/verify is called successfully.",
    )

    class Config:
        use_enum_values = True
        json_encoders  = {datetime: lambda dt: dt.isoformat()}
