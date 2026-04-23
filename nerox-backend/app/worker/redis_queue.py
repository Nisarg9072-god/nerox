from __future__ import annotations

import importlib
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import redis
from bson import ObjectId
from rq import Queue, Retry, Worker, get_current_job

from app.core.config import settings
from app.core.logger import get_logger
from app.db.mongodb import get_sync_database
from app.services.ws_manager import emit_job_failed

logger = get_logger(__name__)

JOBS_COL = "background_jobs"


def _redis_conn() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def _queue() -> Queue:
    return Queue(settings.RQ_QUEUE_NAME, connection=_redis_conn())


def _resolve_callable(module_name: str, qualname: str) -> Callable[..., Any]:
    module = importlib.import_module(module_name)
    fn = module
    for part in qualname.split("."):
        fn = getattr(fn, part)
    return fn


def _update_job_meta(job_id: str, fields: dict[str, Any]) -> None:
    db = get_sync_database()
    db[JOBS_COL].update_one({"job_id": job_id}, {"$set": fields}, upsert=True)


def execute_job(module_name: str, qualname: str, kwargs: dict[str, Any]) -> None:
    job = get_current_job()
    if job is None:
        raise RuntimeError("RQ job context unavailable.")

    t0 = time.perf_counter()
    _update_job_meta(job.id, {
        "status": "processing",
        "started_at": datetime.now(timezone.utc),
        "last_error": None,
        "retries": job.meta.get("retries", 0),
    })

    fn = _resolve_callable(module_name, qualname)
    logger.info(
        "Processing job",
        extra={"event": "job_processing", "job_id": job.id, "target": f"{module_name}.{qualname}"},
    )
    try:
        fn(**kwargs)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        _update_job_meta(job.id, {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc),
            "duration_ms": elapsed_ms,
        })
        logger.info(
            "job_completed",
            extra={"event": "job_completed", "job_id": job.id, "duration_ms": elapsed_ms},
        )
    except Exception as exc:
        retries_done = int(job.meta.get("retries", 0)) + 1
        job.meta["retries"] = retries_done
        job.save_meta()

        _update_job_meta(job.id, {
            "status": "failed" if (job.retries_left or 0) <= 0 else "processing",
            "completed_at": datetime.now(timezone.utc),
            "last_error": str(exc),
            "retries": retries_done,
        })
        logger.error(
            "job_failed",
            extra={
                "event": "job_failed",
                "job_id": job.id,
                "retries_done": retries_done,
                "retries_left": job.retries_left,
                "error": str(exc),
            },
        )
        if (job.retries_left or 0) <= 0:
            uid = kwargs.get("user_id")
            jid = kwargs.get("job_id")
            if not uid and jid:
                try:
                    doc = get_sync_database()["detection_jobs"].find_one({"_id": ObjectId(jid)}, {"user_id": 1})
                    if doc:
                        uid = doc.get("user_id")
                except Exception:
                    pass
            if uid and jid:
                emit_job_failed(user_id=str(uid), job_id=str(jid), reason=str(exc))
        raise


class RedisTaskQueue:
    def enqueue(
        self,
        fn: Callable[..., Any],
        *,
        task_name: str = "unnamed",
        max_retries: Optional[int] = None,
        timeout_sec: Optional[float] = None,
        **kwargs: Any,
    ) -> str:
        queue = _queue()
        retries = settings.MAX_JOB_RETRIES if max_retries is None else max_retries

        job = queue.enqueue(
            execute_job,
            fn.__module__,
            fn.__qualname__,
            kwargs,
            retry=Retry(max=max(0, retries), interval=[2, 4, 8][: max(0, retries)] or [1]),
            job_timeout=int(timeout_sec) if timeout_sec else None,
            result_ttl=86400,
            failure_ttl=86400,
            meta={"task_name": task_name, "retries": 0},
        )

        _update_job_meta(job.id, {
            "job_id": job.id,
            "queue": settings.RQ_QUEUE_NAME,
            "task_name": task_name,
            "status": "pending",
            "retries": 0,
            "max_retries": retries,
            "timeout_sec": timeout_sec,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "kwargs": {k: str(v) for k, v in kwargs.items() if k in {"asset_id", "user_id", "job_id"}},
        })
        logger.info(
            "Job pushed to Redis",
            extra={"event": "job_enqueued", "job_id": job.id, "task_name": task_name, "queue": settings.RQ_QUEUE_NAME},
        )
        return job.id

    async def shutdown(self, timeout: float = 30.0) -> None:
        logger.info("redis_task_queue_shutdown", extra={"event": "redis_task_queue_shutdown", "timeout": timeout})

    def get_status(self, task_id: str) -> Optional[dict[str, Any]]:
        db = get_sync_database()
        return db[JOBS_COL].find_one({"job_id": task_id}, {"_id": 0})

    def metrics(self) -> dict[str, Any]:
        queue = _queue()
        workers = Worker.all(connection=_redis_conn())
        db = get_sync_database()
        completed = db[JOBS_COL].count_documents({"status": "completed"})
        failed = db[JOBS_COL].count_documents({"status": "failed"})
        dur_pipe = [
            {"$match": {"duration_ms": {"$gt": 0}}},
            {"$group": {"_id": None, "avg": {"$avg": "$duration_ms"}}},
        ]
        dur = list(db[JOBS_COL].aggregate(dur_pipe))
        return {
            "queue_size": queue.count,
            "active_workers": len(workers),
            "jobs_processed": completed,
            "jobs_failed": failed,
            "avg_processing_time": round(dur[0]["avg"], 2) if dur else 0.0,
            "avg_job_time": round(dur[0]["avg"], 2) if dur else 0.0,
        }

