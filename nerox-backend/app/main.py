"""
Nerox Backend — FastAPI Entry Point  (v5.0.0 — Phase 5: Invisible Watermarking System)
===================================================================================
Startup sequence (Phases 1–5):
  1. Ensure upload directory exists (static files mount).
  2. Open MongoDB connection.
  3. Create all required database indexes (assets + fingerprints + watermarks collections).
  4. Pre-load FAISS index from all completed embeddings in MongoDB.

Shutdown:
  5. Close MongoDB connection gracefully.
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
from app.db.mongodb import connect_to_mongo, close_mongo_connection
from app.services.storage_service import ensure_upload_dir, UPLOAD_DIR

logger = get_logger(__name__)

# Upload directory must exist before StaticFiles is mounted (module load time)
ensure_upload_dir()


# ---------------------------------------------------------------------------
# Database index setup
# ---------------------------------------------------------------------------

def _create_indexes() -> None:
    """
    Idempotently create all required MongoDB indexes.

    Uses explicit `name=` on every index so PyMongo can match an existing
    index by name and skip creation (no-op).  If an index on the same keys
    already exists under a *different* name (IndexOptionsConflict, code 85)
    we log a warning and continue — the collection is still indexed correctly,
    just under the old name.  Any other OperationFailure is re-raised.
    """
    from pymongo.errors import OperationFailure
    from app.db.mongodb import get_database

    db = get_database()

    # (collection, key_list, index_name)
    index_specs = [
        # assets collection
        ("assets", [("user_id", 1)],                       "idx_assets_user_id"),
        ("assets", [("user_id", 1), ("created_at", -1)],   "idx_assets_user_created"),
        # fingerprints collection
        ("fingerprints", [("asset_id", 1)],                          "idx_fp_asset_id"),
        ("fingerprints", [("user_id", 1)],                           "idx_fp_user_id"),
        ("fingerprints", [("processing_status", 1)],                 "idx_fp_status"),
        ("fingerprints", [("asset_id", 1), ("created_at", -1)],      "idx_fp_asset_created"),
        # watermarks collection (Phase 5)
        ("watermarks", [("asset_id", 1)],                            "idx_wm_asset_id"),
        ("watermarks", [("user_id", 1)],                             "idx_wm_user_id"),
        ("watermarks", [("wm_token", 1)],                            "idx_wm_token"),
        ("watermarks", [("status", 1)],                              "idx_wm_status"),
        ("watermarks", [("asset_id", 1), ("created_at", -1)],        "idx_wm_asset_created"),
        # detections collection (Phase 6)
        ("detections", [("user_id", 1)],                             "idx_det_user_id"),
        ("detections", [("asset_id", 1)],                            "idx_det_asset_id"),
        ("detections", [("detected_at", -1)],                        "idx_det_detected_at"),
        ("detections", [("risk_score", -1)],                         "idx_det_risk_score"),
        ("detections", [("platform_name", 1)],                       "idx_det_platform"),
        ("detections", [("source_type", 1)],                         "idx_det_source_type"),
        ("detections", [("user_id", 1), ("detected_at", -1)],        "idx_det_user_date"),
        ("detections", [("asset_id", 1), ("detected_at", -1)],       "idx_det_asset_date"),
        # alerts collection (Phase 6)
        ("alerts", [("user_id", 1)],                                 "idx_alt_user_id"),
        ("alerts", [("asset_id", 1)],                                "idx_alt_asset_id"),
        ("alerts", [("alert_type", 1)],                              "idx_alt_type"),
        ("alerts", [("severity", 1)],                                "idx_alt_severity"),
        ("alerts", [("resolved", 1)],                                "idx_alt_resolved"),
        ("alerts", [("triggered_at", -1)],                           "idx_alt_triggered_at"),
        ("alerts", [("user_id", 1), ("resolved", 1), ("triggered_at", -1)], "idx_alt_user_active"),
    ]

    for collection, keys, name in index_specs:
        try:
            db[collection].create_index(keys, name=name)
            logger.debug("Index '%s' on '%s' — ready.", name, collection)
        except OperationFailure as exc:
            if exc.code == 85:
                # IndexOptionsConflict: same keys, different name already exists.
                # Existing index still accelerates queries — safe to skip.
                logger.warning(
                    "Index '%s' on '%s': same keys exist under a different name. "
                    "Skipping (performance unaffected).",
                    name, collection,
                )
            elif exc.code == 86:
                # IndexKeySpecsConflict: same name exists but points to DIFFERENT keys.
                # Drop the stale index and recreate with the correct key spec.
                logger.warning(
                    "Index '%s' on '%s': name clash with different key spec. "
                    "Dropping stale index and recreating.",
                    name, collection,
                )
                try:
                    db[collection].drop_index(name)
                    db[collection].create_index(keys, name=name)
                    logger.info("Index '%s' on '%s' — recreated successfully.", name, collection)
                except Exception as drop_exc:
                    logger.error(
                        "Failed to recreate index '%s' on '%s': %s",
                        name, collection, drop_exc,
                    )
            else:
                raise   # unexpected OperationFailure — propagate

    logger.info("MongoDB indexes verified.")



# ---------------------------------------------------------------------------
# Lifespan context manager
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup
    -------
    1. Connect to MongoDB.
    2. Create / verify required indexes.
    3. Pre-load FAISS index with all completed embeddings.
    4. Log Phase 5 watermarking system readiness.

    Shutdown
    --------
    Close MongoDB connection gracefully.
    """
    logger.info("Nerox API v5.0.0 starting up …")

    connect_to_mongo()
    _create_indexes()

    # Pre-populate FAISS with all existing completed embeddings
    try:
        from app.services.vector_service import get_vector_index
        n = get_vector_index().load_from_db()
        logger.info("FAISS index ready — %d embeddings pre-loaded.", n)
    except Exception as exc:
        logger.warning("FAISS pre-load skipped: %s", exc)

    logger.info("Phase 5: Invisible watermarking system ready.")

    yield

    logger.info("Nerox API shutting down …")
    close_mongo_connection()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Nerox API",
    description=(
        "## Nerox — AI-Powered Digital Asset Protection Platform\n\n"
        "**v5.0.0 — Phase 5: Invisible Watermarking + Ownership Trace System**\n\n"
        "### Features\n"
        "- **JWT Authentication** — register, login, protected endpoints\n"
        "- **File Upload** — images (jpg/png) and videos (mp4/mov)\n"
        "- **AI Fingerprinting** — ResNet50 2048-d embeddings; similarity search via FAISS\n"
        "- **Invisible Watermarking** — DCT frequency-domain; survives JPEG Q70+, resize, mild edits\n"
        "- **Ownership Trace** — `POST /watermark/verify` maps leaked content to original owner\n\n"
        "### Recommended Workflow\n"
        "1. `POST /auth/login` → Authorize\n"
        "2. `POST /assets/upload` → note `asset_id`, `fingerprint_id`, `watermark_id`\n"
        "3. `GET /assets/{id}/fingerprint-status` → poll until `completed`\n"
        "4. `GET /assets/{id}/watermark-status`   → poll until `completed`\n"
        "5. `POST /detect`            → similarity search\n"
        "6. `POST /watermark/verify`  → ownership trace"
    ),
    version="5.0.0",
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
def health_check() -> dict:
    """Returns server version, storage backend, FAISS index size, and watermark stats."""
    try:
        from app.services.vector_service import get_vector_index
        faiss_vectors = get_vector_index().total
    except Exception:
        faiss_vectors = -1

    # Watermark statistics
    try:
        from app.db.mongodb import get_database
        db = get_database()
        wm_total     = db["watermarks"].count_documents({})
        wm_completed = db["watermarks"].count_documents({"status": "completed"})
    except Exception:
        wm_total = -1
        wm_completed = -1

    return {
        "status":           "ok",
        "service":          "nerox-api",
        "version":          "5.0.0",
        "storage":          settings.STORAGE_TYPE,
        "faiss_vectors":    faiss_vectors,
        "wm_completed":     wm_completed,
        "wm_total":         wm_total,
    }
