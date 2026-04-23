"""
Nerox Backend — FastAPI Entry Point  (v7.0.0 — Phase 2: Enterprise-Grade Upgrade)
==================================================================================
Startup sequence:
  1. Ensure upload directory exists (static files mount).
  2. Open MongoDB connections (async Motor + sync PyMongo).
  3. Create all required database indexes (including UNIQUE on users.email).
  4. Pre-load FAISS index from all completed embeddings in MongoDB.

Shutdown:
  5. Gracefully shut down background TaskQueue.
  6. Close MongoDB connections.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import auth, assets
from app.api.routes import analytics as analytics_router
from app.api.routes import detect as detect_router
from app.api.routes import watermark as watermark_router
from app.core.config import settings
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

    logger.info("MongoDB indexes verified (Phase 2 — includes unique constraints).")



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
    logger.info("Nerox API v7.0.0 starting up …")

    await connect_to_mongo()
    _create_indexes()

    # Pre-populate FAISS with all existing completed embeddings
    try:
        from app.services.vector_service import get_vector_index
        n = get_vector_index().load_from_db()
        logger.info("FAISS index ready — %d embeddings pre-loaded.", n)
    except Exception as exc:
        logger.warning("FAISS pre-load skipped: %s", exc)

    logger.info("Phase 2: Enterprise-grade backend ready.")

    yield

    logger.info("Nerox API shutting down …")

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
        "**v7.0.0 — Phase 2: Enterprise-Grade Backend Upgrade**\n\n"
        "### Features\n"
        "- **JWT Authentication** — register, login, profile, password management\n"
        "- **File Upload** — images (jpg/png) and videos (mp4/mov)\n"
        "- **AI Fingerprinting** — ResNet50 2048-d embeddings; similarity search via FAISS\n"
        "- **Invisible Watermarking** — DCT frequency-domain; survives JPEG Q70+, resize, mild edits\n"
        "- **Ownership Trace** — `POST /watermark/verify` maps leaked content to original owner\n"
        "- **Async Database** — Motor (non-blocking MongoDB)\n"
        "- **Background Workers** — Production task queue with retry logic\n\n"
        "### Recommended Workflow\n"
        "1. `POST /auth/login` → Authorize\n"
        "2. `POST /assets/upload` → note `asset_id`, `fingerprint_id`, `watermark_id`\n"
        "3. `GET /assets/{id}/fingerprint-status` → poll until `completed`\n"
        "4. `GET /assets/{id}/watermark-status`   → poll until `completed`\n"
        "5. `POST /detect`            → similarity search\n"
        "6. `POST /watermark/verify`  → ownership trace"
    ),
    version="7.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

_CORS_ORIGINS = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"], summary="Liveness probe")
async def health_check() -> dict:
    """Returns server version, storage backend, FAISS index size, and watermark stats."""
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
    except Exception:
        wm_total = -1
        wm_completed = -1

    return {
        "status":           "ok",
        "service":          "nerox-api",
        "version":          "7.0.0",
        "storage":          settings.STORAGE_TYPE,
        "faiss_vectors":    faiss_vectors,
        "wm_completed":     wm_completed,
        "wm_total":         wm_total,
    }
