"""
app/services/detection_service.py
====================================
Service layer for creating and querying detection records.

Public API
----------
  create_detection(...)   → str (detection_id)
    Synchronous — safe to call inside any request handler.
    Steps:
      1. Count prior detections for this asset (for frequency risk score).
      2. Calculate risk score via risk_engine.
      3. Insert detection document into 'detections' collection.
      4. Hand off to alert_service for threshold checking (non-blocking).

  get_detections_for_asset(asset_id, user_id, limit) → list[dict]
    Used by analytics endpoints.

  doc_to_detection_item(doc) → DetectionItem
    Helper for route layers.

Design rules
------------
  • No circular imports — imports only from app.core / app.db / app.services.risk_engine.
  • alert_service is imported lazily inside create_detection to avoid circular dep.
  • All DB operations use get_database() — no module-level connections.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from app.core.logger import get_logger
from app.db.mongodb import get_database
from app.schemas.detection_schema import DetectionItem
from app.services.risk_engine import (
    calculate_risk_score,
    confidence_from_similarity,
    risk_label,
)

logger = get_logger(__name__)

DETECTIONS_COL = "detections"
ASSETS_COL     = "assets"


# ---------------------------------------------------------------------------
# Create detection
# ---------------------------------------------------------------------------

def create_detection(
    asset_id:           str,
    user_id:            str,
    source_type:        str,
    similarity_score:   float,
    platform_name:      str      = "unknown",
    source_url:         Optional[str] = None,
    watermark_verified: bool     = False,
    detected_by_user:   Optional[str] = None,
    confidence_label:   Optional[str] = None,
    notes:              Optional[str] = None,
) -> str:
    """
    Create a detection record and trigger alert checks.

    Args:
        asset_id:           MongoDB ObjectId string of the targeted asset.
        user_id:            MongoDB ObjectId string of the asset owner.
        source_type:        'detect' | 'watermark' | 'scan' | 'manual'
        similarity_score:   Cosine similarity or watermark confidence [0, 1].
        platform_name:      Platform where the infringing content was found.
        source_url:         Direct URL of the infringing content (if known).
        watermark_verified: True when DCT watermark extraction confirmed origin.
        detected_by_user:   ObjectId of the user who triggered the detection.
        confidence_label:   If None, derived from similarity_score automatically.
        notes:              Optional free-text annotation.

    Returns:
        detection_id — MongoDB ObjectId string of the new document.
    """
    db = get_database()

    # ── 1. Frequency count (prior detections for risk scoring) ───────────────
    prior_count: int = db[DETECTIONS_COL].count_documents({"asset_id": asset_id})

    # ── 2. Compute risk score ─────────────────────────────────────────────────
    score = calculate_risk_score(
        similarity_score   = similarity_score,
        watermark_verified = watermark_verified,
        platform_name      = platform_name,
        detection_count    = prior_count,
    )
    label = risk_label(score)
    conf  = confidence_label or confidence_from_similarity(similarity_score)

    # ── 3. Build and insert document ──────────────────────────────────────────
    now = datetime.now(timezone.utc)
    doc = {
        "asset_id":            asset_id,
        "user_id":             user_id,
        "source_type":         source_type,
        "platform_name":       platform_name.lower().strip(),
        "source_url":          source_url,
        "similarity_score":    round(similarity_score, 4),
        "confidence_label":    conf,
        "risk_score":          score,
        "risk_label":          label,
        "watermark_verified":  watermark_verified,
        "detected_by_user":    detected_by_user,
        "verification_status": "pending",
        "notes":               notes,
        "detected_at":         now,
        "created_at":          now,
    }

    try:
        result       = db[DETECTIONS_COL].insert_one(doc)
        detection_id = str(result.inserted_id)
    except Exception as exc:
        logger.error(
            "Failed to insert detection record — asset=%s user=%s: %s",
            asset_id, user_id, exc,
        )
        return ""

    logger.info(
        "Detection created — id=%s asset=%s risk=%d(%s) source=%s wm=%s",
        detection_id, asset_id, score, label, source_type, watermark_verified,
    )

    # ── 4. Trigger alert checks (non-fatal) ──────────────────────────────────
    try:
        from app.services.alert_service import check_and_create_alerts
        doc["_id"]     = result.inserted_id
        doc["id_str"]  = detection_id
        check_and_create_alerts(detection_doc=doc, prior_count=prior_count)
    except Exception as exc:
        logger.warning("Alert check failed for detection=%s: %s", detection_id, exc)

    return detection_id


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_detections_for_asset(
    asset_id: str,
    user_id:  str,
    limit:    int = 50,
) -> List[dict]:
    """Fetch the most recent `limit` detections for a specific asset."""
    db = get_database()
    cursor = (
        db[DETECTIONS_COL]
        .find({"asset_id": asset_id, "user_id": user_id})
        .sort("detected_at", -1)
        .limit(limit)
    )
    return list(cursor)


def doc_to_detection_item(doc: dict) -> DetectionItem:
    """Convert a raw MongoDB detection document to the API schema."""
    return DetectionItem(
        detection_id       = str(doc["_id"]),
        asset_id           = doc["asset_id"],
        user_id            = doc["user_id"],
        source_type        = doc["source_type"],
        platform_name      = doc["platform_name"],
        source_url         = doc.get("source_url"),
        similarity_score   = doc["similarity_score"],
        confidence_label   = doc["confidence_label"],
        risk_score         = doc["risk_score"],
        risk_label         = doc["risk_label"],
        watermark_verified = doc.get("watermark_verified", False),
        verification_status = doc.get("verification_status", "pending"),
        notes              = doc.get("notes"),
        detected_at        = doc["detected_at"],
        created_at         = doc["created_at"],
    )
