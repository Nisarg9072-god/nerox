"""
app/schemas/detection_insights_schema.py
==========================================
Phase 2.6 — Pydantic schemas for GET /analytics/detection-insights.

Provides rich detection analytics including:
  - Daily detection trends with similarity/risk averages
  - Platform breakdown with high-match counts
  - Top attacked assets ranking
  - Confidence distribution (HIGH/MEDIUM/LOW)
  - Source type distribution
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class DailyTrendPoint(BaseModel):
    """Single day in the detection trend."""
    date:           str   = Field(..., description="ISO date YYYY-MM-DD")
    count:          int   = 0
    avg_similarity: float = 0
    avg_risk:       float = 0


class PlatformInsight(BaseModel):
    """Per-platform detection statistics."""
    platform:       str
    count:          int
    percentage:     float
    avg_similarity: float
    avg_risk:       float
    high_matches:   int = Field(0, description="Count of matches with similarity ≥ 0.85")


class TopAttackedAsset(BaseModel):
    """Asset ranked by detection frequency."""
    asset_id:        str
    filename:        str   = "unknown"
    file_type:       str   = "unknown"
    detection_count: int
    avg_similarity:  float
    max_risk:        int
    platforms:       List[str]
    last_detected:   Optional[str] = None


class ConfidenceDistribution(BaseModel):
    """Match confidence breakdown."""
    high:   int = Field(0, description="Matches with similarity ≥ 0.85")
    medium: int = Field(0, description="Matches with similarity 0.70–0.85")
    low:    int = Field(0, description="Matches with similarity < 0.70")


class SourceDistribution(BaseModel):
    """Detection count by source type."""
    source: str
    count:  int


class DetectionInsightsResponse(BaseModel):
    """Full response for GET /analytics/detection-insights."""
    window_days:               int
    total_detections:          int
    avg_similarity:            float
    daily_trend:               List[DailyTrendPoint]
    platform_breakdown:        List[PlatformInsight]
    top_attacked_assets:       List[TopAttackedAsset]
    confidence_distribution:   ConfidenceDistribution
    source_distribution:       List[SourceDistribution]
    total_auto_scans:          int
    completed_auto_scans:      int
    generated_at:              str
