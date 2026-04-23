"""
app/schemas/analytics_schema.py
==================================
Pydantic v2 response schemas for all analytics endpoints.

Designed to be directly consumable by a React/Vue dashboard frontend
without any transformation on the client side.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# GET /analytics/dashboard
# ---------------------------------------------------------------------------

class OverviewStats(BaseModel):
    total_assets:           int   = Field(..., description="Total assets owned by this user.")
    total_detections:       int   = Field(..., description="Total detection events recorded.")
    high_risk_assets:       int   = Field(..., description="Assets with at least one high/critical detection.")
    critical_alerts:        int   = Field(..., description="Unresolved critical-severity alerts.")
    watermark_verifications: int  = Field(..., description="Detections where watermark was verified.")
    detection_rate:         float = Field(..., description="Average detections per asset (to 2 dp).")


class RiskSummary(BaseModel):
    low:      int = 0
    medium:   int = 0
    high:     int = 0
    critical: int = 0


class PlatformStat(BaseModel):
    platform:   str
    count:      int
    percentage: float


class TrendPoint(BaseModel):
    date:  str   = Field(..., description="ISO date string YYYY-MM-DD.")
    count: int


class RecentDetection(BaseModel):
    detection_id:     str
    asset_id:         str
    platform_name:    str
    similarity_score: float
    risk_score:       int
    risk_label:       str
    watermark_verified: bool
    detected_at:      datetime


class TopSource(BaseModel):
    source_url:    str
    detection_count: int
    avg_risk_score: float


class DashboardResponse(BaseModel):
    """Returned by GET /analytics/dashboard."""

    generated_at:          datetime
    overview:              OverviewStats
    risk_summary:          RiskSummary
    platform_distribution: List[PlatformStat]
    recent_detections:     List[RecentDetection]
    trend_last_30_days:    List[TrendPoint]
    top_suspicious_sources: List[TopSource]


# ---------------------------------------------------------------------------
# GET /analytics/assets/high-risk
# ---------------------------------------------------------------------------

class HighRiskAsset(BaseModel):
    asset_id:          str
    original_filename: str
    file_type:         str
    max_risk_score:    int
    avg_risk_score:    float
    detection_count:   int
    watermark_hits:    int     = Field(..., description="Detections where watermark was verified.")
    platforms:         List[str]
    last_detected_at:  Optional[datetime]
    recommendation:    str     = Field(..., description="Recommended action.")


class HighRiskResponse(BaseModel):
    """Returned by GET /analytics/assets/high-risk."""
    total:  int
    assets: List[HighRiskAsset]


# ---------------------------------------------------------------------------
# GET /analytics/timeline
# ---------------------------------------------------------------------------

class TimelinePoint(BaseModel):
    period:     str   = Field(..., description="Period label: YYYY-MM-DD (day) or YYYY-WW (week).")
    count:      int
    avg_risk:   float
    platforms:  List[str]


class TimelineResponse(BaseModel):
    """Returned by GET /analytics/timeline."""
    period_type: str   = Field(..., description="'day' or 'week'.")
    days:        int   = Field(..., description="Number of past days included.")
    total:       int
    points:      List[TimelinePoint]


# ---------------------------------------------------------------------------
# GET /analytics/platforms
# ---------------------------------------------------------------------------

class PlatformDetail(BaseModel):
    platform:        str
    detection_count: int
    percentage:      float
    avg_similarity:  float
    avg_risk_score:  float
    watermark_hits:  int
    severity:        str    = Field(..., description="Platform inherent severity rating.")


class PlatformsResponse(BaseModel):
    """Returned by GET /analytics/platforms."""
    total_detections: int
    platforms:        List[PlatformDetail]


# ---------------------------------------------------------------------------
# Alerts (GET /analytics/alerts)
# ---------------------------------------------------------------------------

class AlertItem(BaseModel):
    alert_id:     str
    alert_type:   str
    asset_id:     str
    severity:     str
    message:      str
    resolved:     bool
    triggered_at: datetime
    resolved_at:  Optional[datetime] = None


class AlertListResponse(BaseModel):
    total:  int
    alerts: List[AlertItem]
