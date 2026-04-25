from __future__ import annotations

from fastapi import APIRouter
import redis

from app.core.config import settings
from app.db.mongodb import get_database
from app.services.task_queue import task_queue

router = APIRouter()


@router.get("/metrics", summary="Distributed queue and worker metrics")
async def system_metrics() -> dict:
    metrics = task_queue.metrics()
    redis_ok = False
    redis_latency_ms = None
    try:
        conn = redis.Redis.from_url(settings.REDIS_URL)
        import time
        start = time.perf_counter()
        conn.ping()
        redis_latency_ms = round((time.perf_counter() - start) * 1000, 2)
        redis_ok = True
    except Exception:
        redis_ok = False
    db = get_database()
    active_jobs = await db["background_jobs"].count_documents({"status": {"$in": ["pending", "processing"]}})
    failed_jobs = await db["background_jobs"].count_documents({"status": "failed"})
    return {
        **metrics,
        "active_jobs": active_jobs,
        "failed_jobs": failed_jobs,
        "worker_status": "ok" if metrics.get("active_workers", 0) > 0 else "down",
        "redis_health": "ok" if redis_ok else "down",
        "redis_latency_ms": redis_latency_ms,
    }

