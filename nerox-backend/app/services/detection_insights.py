"""
app/services/detection_insights.py
=====================================
Phase 2.6 — Detection Analytics Insights Engine.

Provides advanced analytics aggregations:
  - Detection trend per day (configurable window)
  - Platform-wise breakdown with averages
  - Top attacked assets
  - Average similarity score
  - Match confidence distribution
  - Source type distribution

All queries are scoped to the authenticated user's data.
Uses sync PyMongo since it's called via asyncio.to_thread.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from app.core.logger import get_logger
from app.db.mongodb import get_sync_database

logger = get_logger(__name__)

DETECTIONS_COL  = "detections"
ASSETS_COL      = "assets"
DETECTION_JOBS_COL = "detection_jobs"


def get_detection_insights(user_id: str, days: int = 30) -> Dict[str, Any]:
    """
    Build the detection insights payload for a user.

    Returns:
        - daily_trend: Detection counts per day over the window
        - platform_breakdown: Per-platform stats
        - top_attacked_assets: Most-detected assets
        - avg_similarity: Overall average similarity score
        - confidence_distribution: HIGH / MEDIUM / LOW match counts
        - source_distribution: Detection counts by source type
        - total_detections: Total in the window
        - total_auto_scans: Number of auto-detection jobs
    """
    db  = get_sync_database()
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    # ── Daily trend ──────────────────────────────────────────────────────────
    trend_pipeline = [
        {"$match": {"user_id": user_id, "detected_at": {"$gte": since}}},
        {
            "$group": {
                "_id":   {"$dateToString": {"format": "%Y-%m-%d", "date": "$detected_at"}},
                "count": {"$sum": 1},
                "avg_similarity": {"$avg": "$similarity_score"},
                "avg_risk": {"$avg": "$risk_score"},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    trend_raw = {d["_id"]: d for d in db[DETECTIONS_COL].aggregate(trend_pipeline)}

    # Fill all days in the window
    daily_trend = []
    for i in range(days - 1, -1, -1):
        day_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        raw = trend_raw.get(day_str, {})
        daily_trend.append({
            "date":           day_str,
            "count":          raw.get("count", 0),
            "avg_similarity": round(raw.get("avg_similarity", 0), 4),
            "avg_risk":       round(raw.get("avg_risk", 0), 1),
        })

    # ── Platform breakdown ───────────────────────────────────────────────────
    plat_pipeline = [
        {"$match": {"user_id": user_id, "detected_at": {"$gte": since}}},
        {
            "$group": {
                "_id":            "$platform_name",
                "count":          {"$sum": 1},
                "avg_similarity": {"$avg": "$similarity_score"},
                "avg_risk":       {"$avg": "$risk_score"},
                "high_matches":   {
                    "$sum": {"$cond": [{"$gte": ["$similarity_score", 0.85]}, 1, 0]}
                },
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    plat_docs = list(db[DETECTIONS_COL].aggregate(plat_pipeline))
    plat_total = sum(d["count"] for d in plat_docs) or 1

    platform_breakdown = [
        {
            "platform":       d["_id"] or "unknown",
            "count":          d["count"],
            "percentage":     round(d["count"] / plat_total * 100, 1),
            "avg_similarity": round(d["avg_similarity"], 4),
            "avg_risk":       round(d["avg_risk"], 1),
            "high_matches":   d["high_matches"],
        }
        for d in plat_docs
    ]

    # ── Top attacked assets ──────────────────────────────────────────────────
    top_assets_pipeline = [
        {"$match": {"user_id": user_id, "detected_at": {"$gte": since}}},
        {
            "$group": {
                "_id":            "$asset_id",
                "detection_count": {"$sum": 1},
                "avg_similarity": {"$avg": "$similarity_score"},
                "max_risk":       {"$max": "$risk_score"},
                "platforms":      {"$addToSet": "$platform_name"},
                "last_detected":  {"$max": "$detected_at"},
            }
        },
        {"$sort": {"detection_count": -1}},
        {"$limit": 10},
    ]
    top_assets_docs = list(db[DETECTIONS_COL].aggregate(top_assets_pipeline))

    # Enrich with asset metadata
    from bson import ObjectId
    asset_ids_oid = []
    for d in top_assets_docs:
        try:
            asset_ids_oid.append(ObjectId(d["_id"]))
        except Exception:
            pass

    asset_meta = {}
    if asset_ids_oid:
        for doc in db[ASSETS_COL].find(
            {"_id": {"$in": asset_ids_oid}},
            {"_id": 1, "original_filename": 1, "file_type": 1},
        ):
            asset_meta[str(doc["_id"])] = doc

    top_attacked_assets = [
        {
            "asset_id":        d["_id"],
            "filename":        asset_meta.get(d["_id"], {}).get("original_filename", "unknown"),
            "file_type":       asset_meta.get(d["_id"], {}).get("file_type", "unknown"),
            "detection_count": d["detection_count"],
            "avg_similarity":  round(d["avg_similarity"], 4),
            "max_risk":        d["max_risk"],
            "platforms":       list(d["platforms"]),
            "last_detected":   d["last_detected"].isoformat() if d.get("last_detected") else None,
        }
        for d in top_assets_docs
    ]

    # ── Average similarity score ─────────────────────────────────────────────
    avg_sim_pipeline = [
        {"$match": {"user_id": user_id, "detected_at": {"$gte": since}}},
        {"$group": {"_id": None, "avg": {"$avg": "$similarity_score"}, "total": {"$sum": 1}}},
    ]
    avg_sim_result = list(db[DETECTIONS_COL].aggregate(avg_sim_pipeline))
    avg_similarity = round(avg_sim_result[0]["avg"], 4) if avg_sim_result else 0
    total_detections = avg_sim_result[0]["total"] if avg_sim_result else 0

    # ── Confidence distribution ──────────────────────────────────────────────
    conf_pipeline = [
        {"$match": {"user_id": user_id, "detected_at": {"$gte": since}}},
        {
            "$group": {
                "_id": None,
                "high":   {"$sum": {"$cond": [{"$gte": ["$similarity_score", 0.85]}, 1, 0]}},
                "medium": {"$sum": {"$cond": [
                    {"$and": [
                        {"$gte": ["$similarity_score", 0.70]},
                        {"$lt": ["$similarity_score", 0.85]},
                    ]}, 1, 0
                ]}},
                "low":    {"$sum": {"$cond": [{"$lt": ["$similarity_score", 0.70]}, 1, 0]}},
            }
        },
    ]
    conf_result = list(db[DETECTIONS_COL].aggregate(conf_pipeline))
    confidence_distribution = {
        "high":   conf_result[0]["high"] if conf_result else 0,
        "medium": conf_result[0]["medium"] if conf_result else 0,
        "low":    conf_result[0]["low"] if conf_result else 0,
    }

    # ── Source type distribution ─────────────────────────────────────────────
    source_pipeline = [
        {"$match": {"user_id": user_id, "detected_at": {"$gte": since}}},
        {"$group": {"_id": "$source_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    source_distribution = [
        {"source": d["_id"] or "unknown", "count": d["count"]}
        for d in db[DETECTIONS_COL].aggregate(source_pipeline)
    ]

    # ── Auto-scan stats ──────────────────────────────────────────────────────
    total_auto_scans = db[DETECTION_JOBS_COL].count_documents({"user_id": user_id})
    completed_scans = db[DETECTION_JOBS_COL].count_documents(
        {"user_id": user_id, "status": "completed"}
    )

    return {
        "window_days":               days,
        "total_detections":          total_detections,
        "avg_similarity":            avg_similarity,
        "daily_trend":               daily_trend,
        "platform_breakdown":        platform_breakdown,
        "top_attacked_assets":       top_attacked_assets,
        "confidence_distribution":   confidence_distribution,
        "source_distribution":       source_distribution,
        "total_auto_scans":          total_auto_scans,
        "completed_auto_scans":      completed_scans,
        "generated_at":              now.isoformat(),
    }
