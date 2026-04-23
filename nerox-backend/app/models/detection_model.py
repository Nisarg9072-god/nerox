"""
app/models/detection_model.py
================================
Database-layer model for documents in MongoDB's 'detections' collection.

A detection record is created every time a content match is found via:
  - POST /detect (FAISS similarity search)
  - POST /watermark/verify (DCT watermark match)
  - POST /analytics/manual-detection (admin/demo insertion)
  - Future: automated scanning jobs

Collection: detections
Indexes (created at startup):
  - user_id
  - asset_id
  - detected_at   (for timeline queries)
  - risk_score    (for high-risk ranking)
  - platform_name (for platform aggregations)
  - source_type
  - (user_id, detected_at DESC) compound
  - (asset_id, detected_at DESC) compound
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """How the detection was triggered."""
    DETECT    = "detect"     # Via POST /detect (FAISS similarity)
    WATERMARK = "watermark"  # Via POST /watermark/verify
    SCAN      = "scan"       # Future: automated scanning
    MANUAL    = "manual"     # Admin / demo insertion


class ConfidenceLabel(str, Enum):
    """Match confidence level (mirrors watermark + fingerprint labels)."""
    LOW      = "low"
    MEDIUM   = "medium"
    STRONG   = "strong"


class RiskLabel(str, Enum):
    """Risk tier computed by risk_engine.py."""
    LOW      = "low"       # risk_score 0–25
    MEDIUM   = "medium"    # risk_score 26–50
    HIGH     = "high"      # risk_score 51–75
    CRITICAL = "critical"  # risk_score 76–100


class VerificationStatus(str, Enum):
    """Whether the detection has been manually reviewed."""
    PENDING    = "pending"
    VERIFIED   = "verified"
    DISMISSED  = "dismissed"


class DetectionModel(BaseModel):
    """
    Represents a single detection event.

    Fields
    ------
    asset_id            Parent asset (the content being infringed).
    user_id             Owner of the asset.
    source_type         How the detection was triggered.
    platform_name       Where the content was found (inferred or provided).
    source_url          URL of the infringing content (optional).
    similarity_score    Float [0, 1] — cosine similarity or watermark confidence.
    confidence_label    Human-readable match quality tier.
    risk_score          Computed integer [0, 100].
    risk_label          Computed risk tier.
    watermark_verified  True if DCT watermark extraction confirmed ownership.
    detected_by_user    ObjectId string of the user who triggered the detection.
    verification_status Manual review state.
    notes               Free-text notes.
    detected_at         UTC timestamp of the detection event.
    created_at          UTC timestamp of DB record creation.
    """

    asset_id:            str = Field(..., description="Parent asset ObjectId string.")
    user_id:             str = Field(..., description="Asset owner ObjectId string.")
    source_type:         SourceType = Field(default=SourceType.DETECT)
    platform_name:       str = Field(
        default="unknown",
        description="Platform where the content was found (e.g. instagram, youtube).",
    )
    source_url:          Optional[str] = Field(default=None)
    similarity_score:    float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Cosine similarity [0, 1] or watermark confidence.",
    )
    confidence_label:    str = Field(default=ConfidenceLabel.LOW)
    risk_score:          int = Field(
        default=0, ge=0, le=100, description="Computed risk score [0, 100]."
    )
    risk_label:          str = Field(default=RiskLabel.LOW)
    watermark_verified:  bool = Field(
        default=False, description="True when DCT watermark extraction confirmed ownership."
    )
    detected_by_user:    Optional[str] = Field(
        default=None, description="ObjectId of user who triggered the detection (may differ from owner)."
    )
    verification_status: str = Field(default=VerificationStatus.PENDING)
    notes:               Optional[str] = Field(default=None)
    detected_at:         datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    created_at:          datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    class Config:
        use_enum_values = True
        json_encoders  = {datetime: lambda dt: dt.isoformat()}
