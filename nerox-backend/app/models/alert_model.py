"""
app/models/alert_model.py
============================
Database-layer model for documents in MongoDB's 'alerts' collection.

Alerts are generated automatically by alert_service.py whenever a detection
event crosses a severity threshold.  They form the foundation of the future
notification engine (email, webhook, Slack, etc.).

Alert types
-----------
  critical_risk       risk_score >= 76 on any detection
  watermark_verified  DCT watermark extraction confirmed an external copy
  detection_spike     Same asset detected 3+ times within 24 hours
  repeated_misuse     Same asset has accumulated 5+ total detections

Collection: alerts
Indexes (created at startup):
  - user_id
  - asset_id
  - alert_type
  - severity
  - resolved
  - triggered_at
  - (user_id, resolved, triggered_at DESC) — for active-alert dashboard
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AlertType(str, Enum):
    CRITICAL_RISK      = "critical_risk"       # risk_score >= 76
    WATERMARK_VERIFIED = "watermark_verified"  # DCT watermark confirmed external copy
    DETECTION_SPIKE    = "detection_spike"     # 3+ detections in 24h for same asset
    REPEATED_MISUSE    = "repeated_misuse"     # 5+ total detections for same asset


class AlertSeverity(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class AlertModel(BaseModel):
    """
    Represents a single automatically-generated alert.

    Fields
    ------
    alert_type      What condition triggered this alert.
    asset_id        Asset that triggered the alert.
    user_id         Asset owner who should see this alert.
    severity        Severity tier.
    detection_id    The detection document that caused this alert (if applicable).
    message         Human-readable description.
    triggered_at    UTC timestamp of the triggering event.
    resolved        Whether an admin has resolved/dismissed this alert.
    resolved_at     UTC timestamp of resolution.
    created_at      UTC timestamp of DB record creation.
    """

    alert_type:   AlertType = Field(..., description="Type of condition that triggered this alert.")
    asset_id:     str       = Field(..., description="Parent asset ObjectId string.")
    user_id:      str       = Field(..., description="Asset owner ObjectId string.")
    severity:     AlertSeverity = Field(default=AlertSeverity.MEDIUM)
    detection_id: Optional[str] = Field(
        default=None, description="ObjectId of the detection that caused this alert."
    )
    message:      str       = Field(..., description="Human-readable alert description.")
    triggered_at: datetime  = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved:     bool      = Field(default=False)
    resolved_at:  Optional[datetime] = Field(default=None)
    created_at:   datetime  = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        use_enum_values = True
        json_encoders  = {datetime: lambda dt: dt.isoformat()}
