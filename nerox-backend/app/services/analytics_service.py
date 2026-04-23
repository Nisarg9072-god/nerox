"""
app/services/analytics_service.py
=====================================
MongoDB aggregation-based analytics engine for Nerox Phase 6.

All queries are scoped to the authenticated user's data (user_id filter
applied first in every pipeline for index utilization).

Public API
----------
  get_dashboard(user_id)                    → dict (DashboardResponse-compatible)
  get_high_risk_assets(user_id, limit)      → dict (HighRiskResponse-compatible)
  get_timeline(user_id, period, days)       → dict (TimelineResponse-compatible)
  get_platform_breakdown(user_id)           → dict (PlatformsResponse-compatible)

Pipeline design
---------------
  • All $match stages are placed first in every pipeline to utilize indexes.
  • $group / $project follow, then $sort / $limit.
  • datetime.now(timezone.utc) is fetched once per function call (not per pipeline)
    to ensure consistent "most recent" filters.
  • Empty collections return zero-filled responses (never raise 404 for analytics).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.logger import get_logger
from app.db.mongodb import get_database
from app.services.risk_engine import PLATFORM_SEVERITY

logger = get_logger(__name__)

DETECTIONS_COL = "detections"
ASSETS_COL     = "assets"
ALERTS_COL     = "alerts"
WATERMARKS_COL = "watermarks"


# ---------------------------------------------------------------------------
# GET /analytics/dashboard
# ---------------------------------------------------------------------------

def get_dashboard(user_id: str) -> Dict[str, Any]:
    """
    Build the main dashboard payload for a user.

    Contains:
      - Overview statistics
      - Risk summary (count per tier)
      - Platform distribution (top 10)
      - Recent detections (last 10)
      - 30-day daily trend
      - Top suspicious source URLs
    """
    db  = get_database()
    now = datetime.now(timezone.utc)

    # ── Overview counts ────────────────────────────────────────────────────────
    total_assets      = db[ASSETS_COL].count_documents({"user_id": user_id})
    total_detections  = db[DETECTIONS_COL].count_documents({"user_id": user_id})

    # High-risk assets: assets that have at least one high or critical detection
    _high_risk_asset_ids = db[DETECTIONS_COL].distinct(
        "asset_id",
        {"user_id": user_id, "risk_label": {"$in": ["high", "critical"]}},
    )
    high_risk_assets = len(_high_risk_asset_ids)

    critical_alerts  = db[ALERTS_COL].count_documents(
        {"user_id": user_id, "severity": "critical", "resolved": False}
    )
    wm_verifications = db[DETECTIONS_COL].count_documents(
        {"user_id": user_id, "watermark_verified": True}
    )
    detection_rate   = round(total_detections / total_assets, 2) if total_assets > 0 else 0.0

    overview = {
        "total_assets":            total_assets,
        "total_detections":        total_detections,
        "high_risk_assets":        high_risk_assets,
        "critical_alerts":         critical_alerts,
        "watermark_verifications": wm_verifications,
        "detection_rate":          detection_rate,
    }

    # ── Risk summary ──────────────────────────────────────────────────────────
    risk_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$risk_label", "count": {"$sum": 1}}},
    ]
    risk_summary = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for doc in db[DETECTIONS_COL].aggregate(risk_pipeline):
        if doc["_id"] in risk_summary:
            risk_summary[doc["_id"]] = doc["count"]

    # ── Platform distribution ─────────────────────────────────────────────────
    plat_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$platform_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    plat_docs    = list(db[DETECTIONS_COL].aggregate(plat_pipeline))
    plat_total   = sum(d["count"] for d in plat_docs) or 1
    platform_distribution = [
        {
            "platform":   d["_id"] or "unknown",
            "count":      d["count"],
            "percentage": round(d["count"] / plat_total * 100, 1),
        }
        for d in plat_docs
    ]

    # ── Recent detections (last 10) ───────────────────────────────────────────
    recent_cursor = (
        db[DETECTIONS_COL]
        .find({"user_id": user_id})
        .sort("detected_at", -1)
        .limit(10)
    )
    recent_detections = [
        {
            "detection_id":      str(d["_id"]),
            "asset_id":          d["asset_id"],
            "platform_name":     d["platform_name"],
            "similarity_score":  d["similarity_score"],
            "risk_score":        d["risk_score"],
            "risk_label":        d["risk_label"],
            "watermark_verified": d.get("watermark_verified", False),
            "detected_at":       d["detected_at"],
        }
        for d in recent_cursor
    ]

    # ── 30-day daily trend ────────────────────────────────────────────────────
    since_30  = now - timedelta(days=30)
    trend_pipeline = [
        {"$match": {"user_id": user_id, "detected_at": {"$gte": since_30}}},
        {
            "$group": {
                "_id":   {"$dateToString": {"format": "%Y-%m-%d", "date": "$detected_at"}},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    trend_raw  = {d["_id"]: d["count"] for d in db[DETECTIONS_COL].aggregate(trend_pipeline)}
    trend_days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
    trend_last_30_days = [{"date": day, "count": trend_raw.get(day, 0)} for day in trend_days]

    # ── Top suspicious source URLs ────────────────────────────────────────────
    url_pipeline = [
        {"$match": {"user_id": user_id, "source_url": {"$ne": None}}},
        {
            "$group": {
                "_id":           "$source_url",
                "detection_count": {"$sum": 1},
                "avg_risk_score":  {"$avg": "$risk_score"},
            }
        },
        {"$sort": {"detection_count": -1}},
        {"$limit": 5},
    ]
    top_suspicious_sources = [
        {
            "source_url":      d["_id"],
            "detection_count": d["detection_count"],
            "avg_risk_score":  round(d["avg_risk_score"], 1),
        }
        for d in db[DETECTIONS_COL].aggregate(url_pipeline)
    ]

    return {
        "generated_at":           now,
        "overview":               overview,
        "risk_summary":           risk_summary,
        "platform_distribution":  platform_distribution,
        "recent_detections":      recent_detections,
        "trend_last_30_days":     trend_last_30_days,
        "top_suspicious_sources": top_suspicious_sources,
    }


# ---------------------------------------------------------------------------
# GET /analytics/assets/high-risk
# ---------------------------------------------------------------------------

def get_high_risk_assets(user_id: str, limit: int = 20) -> Dict[str, Any]:
    """
    Return the user's assets ranked by maximum risk score (descending).

    For each asset, aggregates:
      - max / avg risk score
      - total detection count
      - watermark verification hit count
      - distinct platforms detected on
      - most recent detection timestamp
    """
    from app.services.risk_engine import recommendation

    db = get_database()

    agg_pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id":             "$asset_id",
                "max_risk_score":  {"$max": "$risk_score"},
                "avg_risk_score":  {"$avg": "$risk_score"},
                "detection_count": {"$sum": 1},
                "watermark_hits":  {"$sum": {"$cond": ["$watermark_verified", 1, 0]}},
                "platforms":       {"$addToSet": "$platform_name"},
                "last_detected":   {"$max": "$detected_at"},
                "max_risk_label":  {"$max": "$risk_label"},
            }
        },
        {"$sort": {"max_risk_score": -1}},
        {"$limit": limit},
    ]
    aggregated = list(db[DETECTIONS_COL].aggregate(agg_pipeline))

    if not aggregated:
        return {"total": 0, "assets": []}

    # Fetch asset metadata for original_filename + file_type
    asset_ids  = [d["_id"] for d in aggregated]
    from bson import ObjectId
    safe_ids   = []
    for aid in asset_ids:
        try:
            safe_ids.append(ObjectId(aid))
        except Exception:
            pass

    asset_meta: Dict[str, dict] = {}
    for adoc in db[ASSETS_COL].find(
        {"_id": {"$in": safe_ids}},
        {"_id": 1, "original_filename": 1, "file_type": 1},
    ):
        asset_meta[str(adoc["_id"])] = adoc

    assets = []
    for d in aggregated:
        aid   = d["_id"]
        meta  = asset_meta.get(aid, {})
        score = int(d["max_risk_score"])
        count = d["detection_count"]
        rec   = recommendation(d.get("max_risk_label", "low"), count)
        assets.append({
            "asset_id":          aid,
            "original_filename": meta.get("original_filename", "unknown"),
            "file_type":         meta.get("file_type", "unknown"),
            "max_risk_score":    score,
            "avg_risk_score":    round(d["avg_risk_score"], 1),
            "detection_count":   count,
            "watermark_hits":    d["watermark_hits"],
            "platforms":         list(d["platforms"]),
            "last_detected_at":  d.get("last_detected"),
            "recommendation":    rec,
        })

    return {"total": len(assets), "assets": assets}


# ---------------------------------------------------------------------------
# GET /analytics/timeline
# ---------------------------------------------------------------------------

def get_timeline(
    user_id: str,
    period:  str = "day",
    days:    int = 30,
) -> Dict[str, Any]:
    """
    Return detection counts grouped by time period.

    Args:
        user_id: Filter scope.
        period:  'day' or 'week'.
        days:    How many past days to include (max 365).
    """
    db    = get_database()
    days  = min(days, 365)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    if period == "week":
        fmt = "%Y-%V"   # ISO year-week
    else:
        fmt = "%Y-%m-%d"

    pipeline = [
        {"$match": {"user_id": user_id, "detected_at": {"$gte": since}}},
        {
            "$group": {
                "_id":       {"$dateToString": {"format": fmt, "date": "$detected_at"}},
                "count":     {"$sum": 1},
                "avg_risk":  {"$avg": "$risk_score"},
                "platforms": {"$addToSet": "$platform_name"},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    points = [
        {
            "period":    d["_id"],
            "count":     d["count"],
            "avg_risk":  round(d["avg_risk"], 1),
            "platforms": list(d["platforms"]),
        }
        for d in db[DETECTIONS_COL].aggregate(pipeline)
    ]
    total = sum(p["count"] for p in points)

    return {
        "period_type": period,
        "days":        days,
        "total":       total,
        "points":      points,
    }


# ---------------------------------------------------------------------------
# GET /analytics/platforms
# ---------------------------------------------------------------------------

def get_platform_breakdown(user_id: str) -> Dict[str, Any]:
    """
    Return a detailed per-platform breakdown of detections.
    """
    db = get_database()

    pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id":            "$platform_name",
                "detection_count": {"$sum": 1},
                "avg_similarity": {"$avg": "$similarity_score"},
                "avg_risk_score": {"$avg": "$risk_score"},
                "watermark_hits": {"$sum": {"$cond": ["$watermark_verified", 1, 0]}},
            }
        },
        {"$sort": {"detection_count": -1}},
    ]

    docs        = list(db[DETECTIONS_COL].aggregate(pipeline))
    grand_total = sum(d["detection_count"] for d in docs) or 1

    platforms = [
        {
            "platform":        d["_id"] or "unknown",
            "detection_count": d["detection_count"],
            "percentage":      round(d["detection_count"] / grand_total * 100, 1),
            "avg_similarity":  round(d["avg_similarity"], 4),
            "avg_risk_score":  round(d["avg_risk_score"], 1),
            "watermark_hits":  d["watermark_hits"],
            "severity":        _platform_severity_label(d["_id"] or "unknown"),
        }
        for d in docs
    ]

    return {
        "total_detections": grand_total if grand_total != 1 else 0,
        "platforms":        platforms,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _platform_severity_label(platform: str) -> str:
    score = PLATFORM_SEVERITY.get(platform.lower(), 7)
    if score >= 18:
        return "critical"
    if score >= 13:
        return "high"
    if score >= 9:
        return "medium"
    return "low"
