"""
Nerox Backend — FastAPI Entry Point  (v8.0.0 — Phase 2.6: Real-Time Intelligence)
==================================================================================
Startup sequence:
  1. Ensure upload directory exists (static files mount).
  2. Open MongoDB connections (async Motor + sync PyMongo).
  3. Create all required database indexes (including UNIQUE on users.email).
  4. Pre-load FAISS index from all completed embeddings in MongoDB.

Shutdown:
  5. Stop the auto-detection scheduler.
  6. Gracefully shut down background TaskQueue.
  7. Close MongoDB connections.
  8. Close WebSocket connections.
"""

from contextlib import asynccontextmanager
import asyncio
import os
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import auth, assets
from app.api.routes import analytics as analytics_router
from app.api.routes import billing as billing_router
from app.api.routes import detect as detect_router
from app.api.routes import saas as saas_router
from app.api.routes import system as system_router
from app.api.routes import watermark as watermark_router
from app.api.routes import ws as ws_router
from app.core.config import settings
from app.core.middleware import request_logging_middleware_factory
from app.core.logger import get_logger
from app.db.mongodb import connect_to_mongo, close_mongo_connection, get_sync_database
from app.services.storage_service import ensure_upload_dir, UPLOAD_DIR

logger = get_logger(__name__)

# Upload directory must exist before StaticFiles is mounted (module load time)
ensure_upload_dir()


# ---------------------------------------------------------------------------
# Database index setup (uses sync client — runs at startup)
# ---------------------------------------------------------------------------

def _create_indexes() -> None:
    """
    Idempotently create all required MongoDB indexes.

    Uses explicit `name=` on every index so PyMongo can match an existing
    index by name and skip creation (no-op).  If an index on the same keys
    already exists under a *different* name (IndexOptionsConflict, code 85)
    we log a warning and continue — the collection is still indexed correctly,
    just under the old name.  Any other OperationFailure is re-raised.

    Phase 2: Added UNIQUE index on users.email for data integrity.
    """
    from pymongo.errors import OperationFailure
    from pymongo import ASCENDING, DESCENDING

    db = get_sync_database()

    # (collection, key_list, index_name, unique)
    index_specs = [
        # ── UNIQUE indexes (Phase 2 — Data Integrity) ────────────────────
        ("users", [("email", ASCENDING)],                     "idx_users_email_unique", True),

        # ── assets collection ─────────────────────────────────────────────
        ("assets", [("user_id", ASCENDING)],                       "idx_assets_user_id",      False),
        ("assets", [("user_id", ASCENDING), ("created_at", DESCENDING)], "idx_assets_user_created", False),
        ("assets", [("created_at", DESCENDING)],                   "idx_assets_created_at",   False),

        # ── fingerprints collection ───────────────────────────────────────
        ("fingerprints", [("asset_id", ASCENDING)],                          "idx_fp_asset_id",      False),
        ("fingerprints", [("user_id", ASCENDING)],                           "idx_fp_user_id",       False),
        ("fingerprints", [("processing_status", ASCENDING)],                 "idx_fp_status",        False),
        ("fingerprints", [("asset_id", ASCENDING), ("created_at", DESCENDING)], "idx_fp_asset_created", False),

        # ── watermarks collection ─────────────────────────────────────────
        ("watermarks", [("asset_id", ASCENDING)],                            "idx_wm_asset_id",      False),
        ("watermarks", [("user_id", ASCENDING)],                             "idx_wm_user_id",       False),
        ("watermarks", [("wm_token", ASCENDING)],                            "idx_wm_token",         False),
        ("watermarks", [("status", ASCENDING)],                              "idx_wm_status",        False),
        ("watermarks", [("asset_id", ASCENDING), ("created_at", DESCENDING)], "idx_wm_asset_created", False),

        # ── detections collection ─────────────────────────────────────────
        ("detections", [("user_id", ASCENDING)],                             "idx_det_user_id",      False),
        ("detections", [("asset_id", ASCENDING)],                            "idx_det_asset_id",     False),
        ("detections", [("detected_at", DESCENDING)],                        "idx_det_detected_at",  False),
        ("detections", [("risk_score", DESCENDING)],                         "idx_det_risk_score",   False),
        ("detections", [("platform_name", ASCENDING)],                       "idx_det_platform",     False),
        ("detections", [("source_type", ASCENDING)],                         "idx_det_source_type",  False),
        ("detections", [("user_id", ASCENDING), ("detected_at", DESCENDING)], "idx_det_user_date",   False),
        ("detections", [("asset_id", ASCENDING), ("detected_at", DESCENDING)], "idx_det_asset_date", False),

        # ── alerts collection ─────────────────────────────────────────────
        ("alerts", [("user_id", ASCENDING)],                                 "idx_alt_user_id",       False),
        ("alerts", [("asset_id", ASCENDING)],                                "idx_alt_asset_id",      False),
        ("alerts", [("alert_type", ASCENDING)],                              "idx_alt_type",          False),
        ("alerts", [("severity", ASCENDING)],                                "idx_alt_severity",      False),
        ("alerts", [("resolved", ASCENDING)],                                "idx_alt_resolved",      False),
        ("alerts", [("triggered_at", DESCENDING)],                           "idx_alt_triggered_at",  False),
        ("alerts", [("user_id", ASCENDING), ("resolved", ASCENDING), ("triggered_at", DESCENDING)], "idx_alt_user_active", False),

        # ── password_reset_tokens (Phase 2) ───────────────────────────────
        ("users", [("reset_token_hash", ASCENDING)],              "idx_users_reset_token", False),

        # ── detection_jobs (Phase 2.5) ────────────────────────────────────
        ("detection_jobs", [("user_id", ASCENDING)],                                       "idx_dj_user_id",      False),
        ("detection_jobs", [("status", ASCENDING)],                                        "idx_dj_status",       False),
        ("detection_jobs", [("created_at", DESCENDING)],                                   "idx_dj_created_at",   False),
        ("detection_jobs", [("user_id", ASCENDING), ("created_at", DESCENDING)],            "idx_dj_user_created", False),
        ("background_jobs", [("job_id", ASCENDING)],                                        "idx_bj_job_id",       True),
        ("background_jobs", [("status", ASCENDING)],                                        "idx_bj_status",       False),
        ("background_jobs", [("created_at", DESCENDING)],                                   "idx_bj_created_at",   False),
        ("organizations", [("owner_user_id", ASCENDING)],                                   "idx_org_owner",       False),
        ("users", [("organization_id", ASCENDING)],                                         "idx_users_org",       False),
        ("usage", [("organization_id", ASCENDING)],                                         "idx_usage_org",       True),
        ("api_keys", [("key", ASCENDING)],                                                  "idx_api_key",         True),
        ("api_keys", [("organization_id", ASCENDING)],                                      "idx_api_key_org",     False),
        ("organizations", [("stripe_customer_id", ASCENDING)],                              "idx_org_stripe_customer", False),
        ("organizations", [("stripe_subscription_id", ASCENDING)],                          "idx_org_stripe_subscription", False),
        ("billing_events", [("event_id", ASCENDING)],                                       "idx_billing_event_id", True),

        # ── Phase 2.6: Enhanced detection indexes ────────────────────────────
        ("detections", [("asset_id", ASCENDING)],                                          "idx_det_asset_id",     False),
        ("detections", [("similarity_score", DESCENDING)],                                 "idx_det_similarity",   False),
        ("detections", [("created_at", DESCENDING)],                                       "idx_det_created_at",   False),
        ("detections", [("detected_at", DESCENDING)],                                      "idx_det_detected_at",  False),
        ("detections", [("user_id", ASCENDING), ("detected_at", DESCENDING)],               "idx_det_user_date",    False),
        ("detections", [("user_id", ASCENDING), ("asset_id", ASCENDING)],                   "idx_det_user_asset",   False),
    ]

    for collection, keys, name, unique in index_specs:
        try:
            db[collection].create_index(keys, name=name, unique=unique)
            logger.debug("Index '%s' on '%s' — ready.", name, collection)
        except OperationFailure as exc:
            if exc.code == 85:
                logger.warning(
                    "Index '%s' on '%s': same keys exist under a different name. "
                    "Skipping (performance unaffected).",
                    name, collection,
                )
            elif exc.code == 86:
                logger.warning(
                    "Index '%s' on '%s': name clash with different key spec. "
                    "Dropping stale index and recreating.",
                    name, collection,
                )
                try:
                    db[collection].drop_index(name)
                    db[collection].create_index(keys, name=name, unique=unique)
                    logger.info("Index '%s' on '%s' — recreated successfully.", name, collection)
                except Exception as drop_exc:
                    logger.error(
                        "Failed to recreate index '%s' on '%s': %s",
                        name, collection, drop_exc,
                    )
            else:
                raise   # unexpected OperationFailure — propagate

    logger.info("MongoDB indexes verified (Phase 2.6 — includes detection optimizations).")


def _run_safe_saas_migration() -> None:
    db = get_sync_database()
    now = datetime.now(timezone.utc)
    users = list(db["users"].find({"$or": [{"organization_id": {"$exists": False}}, {"role": {"$exists": False}}]}))
    for user in users:
        org_doc = {
            "name": user.get("company_name", "Default Organization"),
            "owner_user_id": str(user["_id"]),
            "plan": "free",
            "created_at": now,
        }
        org_id = db["organizations"].insert_one(org_doc).inserted_id
        db["usage"].update_one(
            {"organization_id": str(org_id)},
            {"$setOnInsert": {"organization_id": str(org_id), "scans_used": 0, "uploads_used": 0, "last_reset": now}},
            upsert=True,
        )
        db["users"].update_one(
            {"_id": user["_id"]},
            {"$set": {"organization_id": str(org_id), "role": "owner", "updated_at": now}},
        )


def _warn_if_old_process_running() -> None:
    pid_file = ".nerox_api.pid"
    current_pid = os.getpid()
    try:
        if os.path.exists(pid_file):
            old_pid_raw = open(pid_file, "r", encoding="utf-8").read().strip()
            if old_pid_raw.isdigit():
                old_pid = int(old_pid_raw)
                if old_pid != current_pid:
                    try:
                        os.kill(old_pid, 0)
                        logger.warning("Detected previously running Nerox API process (pid=%s).", old_pid)
                    except Exception:
                        pass
        with open(pid_file, "w", encoding="utf-8") as fh:
            fh.write(str(current_pid))
    except Exception as exc:
        logger.warning("PID drift check failed: %s", exc)



# ---------------------------------------------------------------------------
# Lifespan context manager
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup
    -------
    1. Connect to MongoDB (async + sync).
    2. Create / verify required indexes.
    3. Pre-load FAISS index with all completed embeddings.

    Shutdown
    --------
    4. Shut down background TaskQueue.
    5. Close MongoDB connections.
    """
    logger.info("Nerox API v8.0.0 starting up …")
    import time as _time
    app.state.started_at_epoch = _time.time()

    await connect_to_mongo()
    _warn_if_old_process_running()
    _create_indexes()
    _run_safe_saas_migration()

    # Register main loop for thread-safe WebSocket emissions
    try:
        from app.services.ws_manager import ws_manager
        ws_manager.set_event_loop(asyncio.get_running_loop())
    except Exception as exc:
        logger.warning("WebSocket loop binding failed: %s", exc)

    # Pre-populate FAISS with all existing completed embeddings
    try:
        from app.services.vector_service import get_vector_index
        n = get_vector_index().load_from_db()
        logger.info("FAISS index ready — %d embeddings pre-loaded.", n)
    except Exception as exc:
        logger.warning("FAISS pre-load skipped: %s", exc)

    # Phase 2.5: Start auto-detection scheduler
    try:
        from app.services.scheduler import start_scheduler
        start_scheduler()
    except Exception as exc:
        logger.warning("Auto-detection scheduler failed to start: %s", exc)

    logger.info("Phase 2.5: Auto-Detection Engine ready.")

    # Phase 2.6: Initialize source registry
    try:
        from app.services.ingestion.registry import initialize_default_sources
        initialize_default_sources()
    except Exception as exc:
        logger.warning("Source registry init failed: %s", exc)

    logger.info("Phase 2.6: Real-Time Intelligence Layer ready.")
    logger.info("SaaS routes loaded")
    logger.info("Billing routes loaded")
    route_paths = sorted({getattr(r, "path", "") for r in app.router.routes})
    logger.info("Available routes: %s", route_paths)

    yield

    logger.info("Nerox API shutting down …")

    # Phase 2.5: Stop auto-detection scheduler
    try:
        from app.services.scheduler import stop_scheduler
        await stop_scheduler()
    except Exception as exc:
        logger.warning("Scheduler shutdown error: %s", exc)

    # Graceful shutdown of background task system
    try:
        from app.services.task_queue import task_queue
        await task_queue.shutdown(timeout=30.0)
    except Exception as exc:
        logger.warning("TaskQueue shutdown error: %s", exc)

    await close_mongo_connection()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Nerox API",
    description=(
        "## Nerox — AI-Powered Digital Asset Protection Platform\n\n"
        "**v8.0.0 — Phase 2.6: Real-Time Intelligence & Scalable Detection**\n\n"
        "### Features\n"
        "- **JWT Authentication** — register, login, profile, password management\n"
        "- **File Upload** — images (jpg/png) and videos (mp4/mov)\n"
        "- **AI Fingerprinting** — ResNet50 2048-d embeddings; similarity search via FAISS\n"
        "- **Invisible Watermarking** — DCT frequency-domain; survives JPEG Q70+, resize, mild edits\n"
        "- **Ownership Trace** — `POST /watermark/verify` maps leaked content to original owner\n"
        "- **Auto-Detection** — Scheduled crawling of YouTube + web for asset misuse\n"
        "- **Real-Time Alerts** — WebSocket live notifications for detections\n"
        "- **Detection Intelligence** — Priority scoring, smart match filtering, confidence classification\n"
        "- **Background Workers** — Production task queue with parallel processing\n\n"
        "### Recommended Workflow\n"
        "1. `POST /auth/login` → Authorize\n"
        "2. `POST /assets/upload` → note `asset_id`, `fingerprint_id`, `watermark_id`\n"
        "3. `GET /assets/{id}/fingerprint-status` → poll until `completed`\n"
        "4. `GET /assets/{id}/watermark-status`   → poll until `completed`\n"
        "5. `POST /detect`            → similarity search\n"
        "6. `POST /detect/auto/start` → auto-scan external sources\n"
        "7. `WS /ws/notifications`    → real-time WebSocket events\n"
        "8. `POST /watermark/verify`  → ownership trace"
    ),
    version="8.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

if settings.ENVIRONMENT.lower() == "production":
    _CORS_ORIGINS = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
else:
    _CORS_ORIGINS = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
allowed_hosts = [h.strip() for h in settings.ALLOWED_HOSTS.split(",") if h.strip()]
if allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
app.middleware("http")(request_logging_middleware_factory())


# ---------------------------------------------------------------------------
# Standardised error handlers  →  {"error": "...", "code": <status>}
# ---------------------------------------------------------------------------

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    logger.warning(
        "HTTP %d on %s %s — %s",
        exc.status_code, request.method, request.url.path, exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "code": exc.status_code},
        headers=getattr(exc, "headers", None) or {},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        f"{' → '.join(str(l) for l in e['loc'])}: {e['msg']}"
        for e in exc.errors()
    ]
    detail = "; ".join(errors)
    logger.warning(
        "Validation error on %s %s — %s", request.method, request.url.path, detail
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": detail, "code": status.HTTP_422_UNPROCESSABLE_ENTITY},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception(
        "Unhandled exception on %s %s: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "An internal server error occurred. Please try again later.",
            "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        },
    )


# ---------------------------------------------------------------------------
# Static file serving  /uploads/<filename>
# ---------------------------------------------------------------------------

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth.router,              prefix="/auth",       tags=["Authentication"])
app.include_router(assets.router,            prefix="/assets",     tags=["Assets"])
app.include_router(detect_router.router,     prefix="/detect",     tags=["Detection"])
app.include_router(watermark_router.router,  prefix="/watermark",  tags=["Watermark"])
app.include_router(analytics_router.router,  prefix="/analytics",  tags=["Analytics"])
app.include_router(ws_router.router,         prefix="/ws",         tags=["WebSocket"])
app.include_router(system_router.router,     prefix="/system",     tags=["System"])
app.include_router(saas_router.router,       prefix="",            tags=["SaaS"])
app.include_router(billing_router.router,    prefix="/billing",    tags=["Billing"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"], summary="Liveness probe")
async def health_check() -> dict:
    """Returns server version, storage backend, FAISS index size, and watermark stats."""
    mongo_ok = False
    redis_ok = False
    workers_ok = False
    try:
        from app.services.vector_service import get_vector_index
        faiss_vectors = get_vector_index().total
    except Exception:
        faiss_vectors = -1

    # Watermark statistics (async)
    try:
        from app.db.mongodb import get_database
        db = get_database()
        wm_total     = await db["watermarks"].count_documents({})
        wm_completed = await db["watermarks"].count_documents({"status": "completed"})
        await db.command("ping")
        mongo_ok = True
    except Exception:
        wm_total = -1
        wm_completed = -1

    try:
        from app.services.task_queue import task_queue
        metrics = task_queue.metrics()
        redis_ok = True
        workers_ok = metrics.get("active_workers", 0) > 0
    except Exception:
        metrics = {"active_workers": 0}

    import time as _time
    uptime_sec = int(_time.time() - app.state.started_at_epoch) if hasattr(app.state, "started_at_epoch") else 0
    return {
        "status":           "ok" if mongo_ok and redis_ok else "degraded",
        "service":          "nerox-api",
        "version":          "8.0.0",
        "storage":          settings.STORAGE_TYPE,
        "faiss_vectors":    faiss_vectors,
        "auto_detect":      bool(settings.YOUTUBE_API_KEY),
        "websocket":        True,
        "wm_completed":     wm_completed,
        "wm_total":         wm_total,
        "services": {
            "mongodb": "ok" if mongo_ok else "down",
            "redis": "ok" if redis_ok else "down",
            "worker": "ok" if workers_ok else "down",
        },
        "active_workers": metrics.get("active_workers", 0),
        "uptime": f"{uptime_sec}s",
    }
