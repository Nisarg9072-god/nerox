"""
app/services/alert_service.py
================================
Alert generation engine for Nerox Phase 6.

Called by detection_service.create_detection() after every new detection.
Runs synchronously but is non-fatal — exceptions are caught and logged.

Alert conditions checked (in order)
------------------------------------
1. risk_score >= 76           → AlertType.CRITICAL_RISK   (CRITICAL)
2. watermark_verified = True  → AlertType.WATERMARK_VERIFIED (HIGH)
3. Same asset ≥ 3 detections in 24h → AlertType.DETECTION_SPIKE (HIGH)
4. Total asset detections ≥ 5 → AlertType.REPEATED_MISUSE (MEDIUM)

Deduplication
-------------
  Before inserting each alert, we check whether an IDENTICAL un-resolved alert
  (same asset_id + alert_type + resolved=False) already exists.
  If so, we skip to avoid alert spam.
  Exception: DETECTION_SPIKE is checked every time (new count may be higher).

Public API
----------
  check_and_create_alerts(detection_doc, prior_count) → None
  get_active_alerts(user_id, limit)                   → list[dict]
  resolve_alert(alert_id, user_id)                    → bool
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId

from app.core.logger import get_logger
from app.db.mongodb import get_sync_database as get_database

logger = get_logger(__name__)

ALERTS_COL     = "alerts"
DETECTIONS_COL = "detections"


# ---------------------------------------------------------------------------
# Alert creation helper
# ---------------------------------------------------------------------------

def _create_alert(
    alert_type:   str,
    asset_id:     str,
    user_id:      str,
    severity:     str,
    message:      str,
    detection_id: Optional[str] = None,
    deduplicate:  bool = True,
) -> Optional[str]:
    """
    Insert an alert document into MongoDB.

    Args:
        deduplicate: If True, skip if an identical unresolved alert exists.

    Returns:
        alert_id string if created, None if skipped.
    """
    db = get_database()

    if deduplicate:
        existing = db[ALERTS_COL].find_one(
            {"asset_id": asset_id, "alert_type": alert_type, "resolved": False}
        )
        if existing:
            logger.debug(
                "Alert deduplicated — type=%s asset=%s (already active)", alert_type, asset_id
            )
            return None

    now = datetime.now(timezone.utc)
    doc = {
        "alert_type":   alert_type,
        "asset_id":     asset_id,
        "user_id":      user_id,
        "severity":     severity,
        "detection_id": detection_id,
        "message":      message,
        "triggered_at": now,
        "resolved":     False,
        "resolved_at":  None,
        "created_at":   now,
    }

    result   = db[ALERTS_COL].insert_one(doc)
    alert_id = str(result.inserted_id)

    logger.info(
        "Alert created — id=%s type=%s severity=%s asset=%s",
        alert_id, alert_type, severity, asset_id,
    )
    logger.info("Alert created for asset: %s", asset_id)
    try:
        from app.services.ws_manager import emit_alert_created
        emit_alert_created(
            user_id=user_id,
            alert_type=alert_type,
            severity=severity,
            asset_id=asset_id,
            message=message,
            alert={
                "alert_id": alert_id,
                "alert_type": alert_type,
                "severity": severity,
                "asset_id": asset_id,
                "message": message,
                "resolved": False,
                "triggered_at": now.isoformat(),
            },
        )
    except Exception:
        pass
    return alert_id


# ---------------------------------------------------------------------------
# Main check function
# ---------------------------------------------------------------------------

def check_and_create_alerts(
    detection_doc: dict,
    prior_count:   int,
) -> None:
    """
    Evaluate all alert conditions for a newly created detection event.

    Called synchronously from detection_service after DB insert.
    Exceptions are swallowed to prevent blocking the request.

    Args:
        detection_doc: The raw detection document (must include _id, asset_id, etc.)
        prior_count:   Number of detections that existed before this one.
    """
    asset_id     = detection_doc["asset_id"]
    user_id      = detection_doc["user_id"]
    risk_score   = detection_doc["risk_score"]
    wm_verified  = detection_doc.get("watermark_verified", False)
    detection_id = detection_doc.get("id_str") or str(detection_doc.get("_id", ""))
    similarity = float(detection_doc.get("similarity_score", 0.0))

    # ── 0. First detection baseline alert ─────────────────────────────────────
    if prior_count == 0:
        _create_alert(
            alert_type="first_detection",
            asset_id=asset_id,
            user_id=user_id,
            severity="medium",
            detection_id=detection_id,
            message=(
                f"First unauthorized detection found for asset {asset_id}. "
                "Review and decide whether to monitor or escalate."
            ),
        )

    # ── 1. Critical risk ───────────────────────────────────────────────────────
    if risk_score >= 76 or (similarity >= 0.90 and prior_count >= 2):
        _create_alert(
            alert_type   = "critical_risk",
            asset_id     = asset_id,
            user_id      = user_id,
            severity     = "critical",
            detection_id = detection_id,
            message      = (
                f"Critical risk score {risk_score}/100 detected for asset {asset_id}. "
                "Immediate action required — consider filing a DMCA takedown."
            ),
        )

    # ── 2. Watermark verified ─────────────────────────────────────────────────
    if wm_verified:
        _create_alert(
            alert_type   = "watermark_verified",
            asset_id     = asset_id,
            user_id      = user_id,
            severity     = "high",
            detection_id = detection_id,
            message      = (
                f"Invisible watermark confirmed: asset {asset_id} found externally. "
                "Cryptographic proof of ownership available."
            ),
            deduplicate  = False,  # Always log — each watermark verification is distinct
        )

    # ── 3. Detection spike (3+ in 24h) ────────────────────────────────────────
    try:
        db          = get_database()
        since_24h   = datetime.now(timezone.utc) - timedelta(hours=24)
        spike_count = db[DETECTIONS_COL].count_documents(
            {"asset_id": asset_id, "detected_at": {"$gte": since_24h}}
        )
        if spike_count >= 3:
            # Drop old spike alert before creating fresh one (new count matters)
            db[ALERTS_COL].delete_one(
                {"asset_id": asset_id, "alert_type": "detection_spike", "resolved": False}
            )
            _create_alert(
                alert_type   = "detection_spike",
                asset_id     = asset_id,
                user_id      = user_id,
                severity     = "high",
                detection_id = detection_id,
                message      = (
                    f"Detection spike: asset {asset_id} was detected {spike_count} times "
                    "in the last 24 hours. Possible coordinated redistribution."
                ),
                deduplicate  = False,
            )
    except Exception as exc:
        logger.warning("Spike check failed for asset=%s: %s", asset_id, exc)

    # ── 4. Repeated misuse (5+ total) ─────────────────────────────────────────
    total_count = prior_count + 1  # include this detection
    if total_count == 5:           # fire exactly once at this threshold
        _create_alert(
            alert_type   = "repeated_misuse",
            asset_id     = asset_id,
            user_id      = user_id,
            severity     = "medium",
            detection_id = detection_id,
            message      = (
                f"Asset {asset_id} has been detected {total_count} times in total. "
                "Systematic misuse pattern identified — consider proactive takedowns."
            ),
        )


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_active_alerts(user_id: str, limit: int = 50) -> list[dict]:
    """Return the most recent unresolved alerts for a user."""
    db = get_database()
    return list(
        db[ALERTS_COL]
        .find({"user_id": user_id, "resolved": False})
        .sort("triggered_at", -1)
        .limit(limit)
    )


def resolve_alert(alert_id: str, user_id: str) -> bool:
    """
    Mark an alert as resolved.

    Returns:
        True if the alert was found and updated; False otherwise.
    """
    try:
        oid = ObjectId(alert_id)
    except Exception:
        return False

    db  = get_database()
    res = db[ALERTS_COL].update_one(
        {"_id": oid, "user_id": user_id},
        {"$set": {"resolved": True, "resolved_at": datetime.now(timezone.utc)}},
    )
    return res.matched_count > 0
