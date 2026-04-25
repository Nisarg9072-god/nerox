"""
app/api/routes/analytics.py
==============================
Phase 6 Analytics + Piracy Spread Tracking endpoints.
Phase 2: All handlers converted to async.

All endpoints require JWT authentication and are scoped to the authenticated
user's data. They never return data belonging to other users.

Routes
------
  GET  /analytics/dashboard           Overview + risk + platform + trend
  GET  /analytics/assets/high-risk    Top risky assets ranked by score
  GET  /analytics/timeline            Chronological spread timeline (day/week)
  GET  /analytics/platforms           Piracy distribution by platform
  GET  /analytics/alerts              Active unresolved alerts
  POST /analytics/alerts/{id}/resolve Mark an alert as resolved
  POST /analytics/manual-detection    Insert a detection event (admin/demo)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.dependencies import get_current_user
from app.core.logger import get_logger
from app.db.mongodb import get_database, get_sync_database
from app.schemas.analytics_schema import (
    AlertItem,
    AlertListResponse,
    DashboardResponse,
    HighRiskAsset,
    HighRiskResponse,
    OverviewStats,
    PlatformDetail,
    PlatformsResponse,
    RiskSummary,
    TimelineResponse,
    TopSource,
    TrendPoint,
    RecentDetection,
    PlatformStat,
    TimelinePoint,
)
from app.schemas.detection_schema import DetectionCreate, DetectionItem
from app.services.alert_service import get_active_alerts, resolve_alert
from app.services.analytics_service import (
    get_dashboard,
    get_high_risk_assets,
    get_platform_breakdown,
    get_timeline,
)
from app.services.detection_service import create_detection, doc_to_detection_item

logger = get_logger(__name__)
router = APIRouter()

ASSETS_COL     = "assets"
DETECTIONS_COL = "detections"
ALERTS_COL     = "alerts"


# ---------------------------------------------------------------------------
# GET /analytics/detection-insights  (Phase 2.6)
# ---------------------------------------------------------------------------

from app.schemas.detection_insights_schema import (
    DetectionInsightsResponse,
    DailyTrendPoint,
    PlatformInsight,
    TopAttackedAsset,
    ConfidenceDistribution,
    SourceDistribution,
)
from app.services.detection_insights import get_detection_insights


@router.get(
    "/detection-insights",
    response_model=DetectionInsightsResponse,
    summary="Detection analytics insights",
    description=(
        "Returns rich detection analytics including:\\n\\n"
        "- **Daily trend**: detection count + avg similarity + avg risk per day\\n"
        "- **Platform breakdown**: per-platform stats with high-match counts\\n"
        "- **Top attacked assets**: most frequently detected assets\\n"
        "- **Average similarity**: overall mean similarity score\\n"
        "- **Confidence distribution**: HIGH / MEDIUM / LOW match counts\\n"
        "- **Source distribution**: detection counts by source type\\n"
        "- **Auto-scan stats**: total and completed auto-detection jobs\\n\\n"
        "All data is scoped to the authenticated user."
    ),
)
async def detection_insights(
    current_user: Annotated[dict, Depends(get_current_user)],
    days: int = Query(default=30, ge=1, le=365, description="Window in days."),
) -> DetectionInsightsResponse:
    user_id = str(current_user["_id"])

    try:
        data = await asyncio.to_thread(get_detection_insights, user_id, days)
    except Exception as exc:
        logger.exception("Detection insights failed — user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate detection insights.",
        )

    return DetectionInsightsResponse(
        window_days=data["window_days"],
        total_detections=data["total_detections"],
        avg_similarity=data["avg_similarity"],
        daily_trend=[DailyTrendPoint(**d) for d in data["daily_trend"]],
        platform_breakdown=[PlatformInsight(**p) for p in data["platform_breakdown"]],
        top_attacked_assets=[TopAttackedAsset(**a) for a in data["top_attacked_assets"]],
        confidence_distribution=ConfidenceDistribution(**data["confidence_distribution"]),
        source_distribution=[SourceDistribution(**s) for s in data["source_distribution"]],
        total_auto_scans=data["total_auto_scans"],
        completed_auto_scans=data["completed_auto_scans"],
        generated_at=data["generated_at"],
    )


# ---------------------------------------------------------------------------
# GET /analytics/dashboard
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Main analytics dashboard",
    description=(
        "Returns a complete analytics payload including:\n\n"
        "- **Overview stats**: asset count, detection count, high-risk count, alerts\n"
        "- **Risk summary**: counts per risk tier (low/medium/high/critical)\n"
        "- **Platform distribution**: top 10 platforms with percentage share\n"
        "- **Recent detections**: last 10 detection events\n"
        "- **30-day trend**: daily detection counts for the past month\n"
        "- **Top suspicious sources**: most frequently detected URLs\n\n"
        "All data is scoped to the authenticated user's assets only."
    ),
)
async def dashboard(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> DashboardResponse:
    user_id = str(current_user["_id"])

    try:
        data = await asyncio.to_thread(get_dashboard, user_id)
    except Exception as exc:
        logger.exception("Dashboard aggregation failed — user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to aggregate dashboard data. Please try again.",
        )

    ov = data["overview"]
    return DashboardResponse(
        generated_at   = data["generated_at"],
        overview       = OverviewStats(
            total_assets            = ov["total_assets"],
            total_detections        = ov["total_detections"],
            high_risk_assets        = ov["high_risk_assets"],
            critical_alerts         = ov["critical_alerts"],
            watermark_verifications = ov["watermark_verifications"],
            detection_rate          = ov["detection_rate"],
            scans_used              = ov.get("scans_used", 0),
            scans_limit             = ov.get("scans_limit"),
            uploads_used            = ov.get("uploads_used", 0),
            uploads_limit           = ov.get("uploads_limit"),
        ),
        risk_summary   = RiskSummary(**data["risk_summary"]),
        platform_distribution = [
            PlatformStat(**p) for p in data["platform_distribution"]
        ],
        recent_detections = [
            RecentDetection(**d) for d in data["recent_detections"]
        ],
        trend_last_30_days = [
            TrendPoint(**t) for t in data["trend_last_30_days"]
        ],
        top_suspicious_sources = [
            TopSource(**s) for s in data["top_suspicious_sources"]
        ],
    )


# ---------------------------------------------------------------------------
# GET /analytics/assets/high-risk
# ---------------------------------------------------------------------------

@router.get(
    "/assets/high-risk",
    response_model=HighRiskResponse,
    summary="High-risk asset ranking",
    description=(
        "Returns the user's assets ranked by **maximum risk score** (descending). "
        "Each entry includes:\n\n"
        "- Max and average risk score across all detections\n"
        "- Total detection count and watermark verification hits\n"
        "- Platforms where the asset was detected\n"
        "- Most recent detection timestamp\n"
        "- Recommended action (monitor / takedown / escalate)\n\n"
        "Only assets with at least one detection record are returned."
    ),
)
async def high_risk_assets(
    current_user: Annotated[dict, Depends(get_current_user)],
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results to return."),
) -> HighRiskResponse:
    user_id = str(current_user["_id"])

    try:
        data = await asyncio.to_thread(get_high_risk_assets, user_id, limit)
    except Exception as exc:
        logger.exception("High-risk aggregation failed — user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to aggregate high-risk assets.",
        )

    return HighRiskResponse(
        total  = data["total"],
        assets = [HighRiskAsset(**a) for a in data["assets"]],
    )


# ---------------------------------------------------------------------------
# GET /analytics/timeline
# ---------------------------------------------------------------------------

@router.get(
    "/timeline",
    response_model=TimelineResponse,
    summary="Detection spread timeline",
    description=(
        "Returns detection counts grouped by **day** or **week** over the specified window.\n\n"
        "Each point includes:\n"
        "- Period label (YYYY-MM-DD for day, ISO YYYY-WW for week)\n"
        "- Detection count for that period\n"
        "- Average risk score\n"
        "- Distinct platforms detected in that period\n\n"
        "Use `period=week` for long-term piracy growth trends."
    ),
)
async def timeline(
    current_user: Annotated[dict, Depends(get_current_user)],
    period: str = Query(
        default="day",
        description="Grouping period: 'day' or 'week'.",
        pattern="^(day|week)$",
    ),
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Number of past days to include.",
    ),
) -> TimelineResponse:
    user_id = str(current_user["_id"])

    try:
        data = await asyncio.to_thread(get_timeline, user_id, period, days)
    except Exception as exc:
        logger.exception("Timeline aggregation failed — user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to aggregate timeline data.",
        )

    return TimelineResponse(
        period_type = data["period_type"],
        days        = data["days"],
        total       = data["total"],
        points      = [TimelinePoint(**p) for p in data["points"]],
    )


# ---------------------------------------------------------------------------
# GET /analytics/platforms
# ---------------------------------------------------------------------------

@router.get(
    "/platforms",
    response_model=PlatformsResponse,
    summary="Piracy distribution by platform",
    description=(
        "Returns a breakdown of all detection events grouped by platform. "
        "For each platform:\n\n"
        "- Detection count and percentage share\n"
        "- Average similarity score and risk score\n"
        "- Watermark verification hit count\n"
        "- Platform severity rating (based on DMCA enforcement + reach)\n\n"
        "Sorted by detection count (highest first)."
    ),
)
async def platforms(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> PlatformsResponse:
    user_id = str(current_user["_id"])

    try:
        data = await asyncio.to_thread(get_platform_breakdown, user_id)
    except Exception as exc:
        logger.exception("Platform aggregation failed — user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to aggregate platform data.",
        )

    return PlatformsResponse(
        total_detections = data["total_detections"],
        platforms        = [PlatformDetail(**p) for p in data["platforms"]],
    )


# ---------------------------------------------------------------------------
# GET /analytics/alerts
# ---------------------------------------------------------------------------

@router.get(
    "/alerts",
    response_model=AlertListResponse,
    summary="Active alerts for the current user",
    description=(
        "Returns all unresolved alerts triggered for the authenticated user's assets.\n\n"
        "Alert types:\n"
        "- `critical_risk` — risk score ≥ 76\n"
        "- `watermark_verified` — DCT watermark extraction confirmed external copy\n"
        "- `detection_spike` — 3+ detections in 24 hours\n"
        "- `repeated_misuse` — 5+ total detections\n\n"
        "Use `POST /analytics/alerts/{id}/resolve` to dismiss an alert."
    ),
)
async def get_alerts(
    current_user: Annotated[dict, Depends(get_current_user)],
    limit: int = Query(default=50, ge=1, le=200),
) -> AlertListResponse:
    user_id = str(current_user["_id"])
    docs    = await asyncio.to_thread(get_active_alerts, user_id, limit)

    items = [
        AlertItem(
            alert_id     = str(d["_id"]),
            alert_type   = d["alert_type"],
            asset_id     = d["asset_id"],
            severity     = d["severity"],
            message      = d["message"],
            resolved     = d["resolved"],
            triggered_at = d["triggered_at"],
            resolved_at  = d.get("resolved_at"),
        )
        for d in docs
    ]
    return AlertListResponse(total=len(items), alerts=items)


# ---------------------------------------------------------------------------
# POST /analytics/alerts/{alert_id}/resolve
# ---------------------------------------------------------------------------

@router.post(
    "/alerts/{alert_id}/resolve",
    summary="Resolve (dismiss) an alert",
    description="Mark an alert as resolved. Only the asset owner can resolve their own alerts.",
    responses={
        200: {"description": "Alert resolved successfully"},
        403: {"description": "Alert belongs to a different user"},
        404: {"description": "Alert not found"},
    },
)
async def resolve_alert_endpoint(
    alert_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    user_id = str(current_user["_id"])
    ok      = await asyncio.to_thread(resolve_alert, alert_id, user_id)

    if not ok:
        # Either not found or doesn't belong to user
        db = get_sync_database()
        try:
            exists = db[ALERTS_COL].find_one({"_id": ObjectId(alert_id)})
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid alert ID format.",
            )
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This alert does not belong to you.",
        )

    return {"message": "Alert resolved successfully.", "alert_id": alert_id}


# ---------------------------------------------------------------------------
# POST /analytics/manual-detection
# ---------------------------------------------------------------------------

@router.post(
    "/manual-detection",
    response_model=DetectionItem,
    status_code=status.HTTP_201_CREATED,
    summary="Manually insert a detection event (admin / demo)",
    description=(
        "Allows manual insertion of simulated detection events for testing or client demos.\n\n"
        "The asset must belong to the authenticated user. "
        "Risk score is computed automatically from the provided `similarity_score`, "
        "`platform_name`, and `watermark_verified` values.\n\n"
        "This endpoint integrates with the alert engine — "
        "high-risk manual detections will generate real alerts."
    ),
    responses={
        201: {"description": "Detection created and risk computed"},
        403: {"description": "Asset belongs to a different user"},
        404: {"description": "Asset not found"},
    },
)
async def manual_detection(
    body: DetectionCreate,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> DetectionItem:
    user_id = str(current_user["_id"])
    db      = get_sync_database()

    # ── Validate asset ownership ──────────────────────────────────────────────
    try:
        oid   = ObjectId(body.asset_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid asset_id format.",
        )

    asset = db[ASSETS_COL].find_one({"_id": oid})
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")
    if asset["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Asset does not belong to you.",
        )

    # ── Create detection ──────────────────────────────────────────────────────
    detection_id = create_detection(
        asset_id           = body.asset_id,
        user_id            = user_id,
        source_type        = "manual",
        similarity_score   = body.similarity_score,
        platform_name      = body.platform_name,
        source_url         = body.source_url,
        watermark_verified = body.watermark_verified,
        detected_by_user   = user_id,
        confidence_label   = body.confidence_label,
        notes              = body.notes,
    )

    if not detection_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create detection record.",
        )

    doc = db[DETECTIONS_COL].find_one({"_id": ObjectId(detection_id)})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Detection created but could not be retrieved.",
        )

    logger.info(
        "Manual detection created — id=%s asset=%s platform=%s user=%s",
        detection_id, body.asset_id, body.platform_name, user_id,
    )
    return doc_to_detection_item(doc)
