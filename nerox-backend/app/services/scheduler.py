"""
app/services/scheduler.py
============================
Phase 2.5 — Background Scheduler for Automated Detection.

Uses a simple asyncio-based scheduling loop (Option B from spec) that:
  - Runs every AUTO_SCAN_INTERVAL_MIN minutes
  - Picks active users with completed assets
  - Creates detection jobs for each user's assets
  - Dispatches jobs to the TaskQueue

Lifecycle:
  - start_scheduler() → called at app startup (lifespan)
  - stop_scheduler()  → called at app shutdown (lifespan)

The scheduler is non-blocking and integrates with FastAPI's event loop.
If the scheduler fails for one user, it logs the error and continues
with the next user — it never crashes the server.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_scheduler_task: Optional[asyncio.Task] = None
_shutdown_event = asyncio.Event()


async def _scheduler_loop() -> None:
    """
    Main scheduler loop — runs indefinitely until shutdown.

    Every tick:
      1. Find users with completed assets
      2. For each user, create a YouTube scan job (expandable)
      3. Dispatch to TaskQueue
    """
    interval = settings.AUTO_SCAN_INTERVAL_MIN * 60  # Convert to seconds
    logger.info(
        "Auto-detection scheduler started — interval=%d min",
        settings.AUTO_SCAN_INTERVAL_MIN,
    )

    while not _shutdown_event.is_set():
        try:
            await _run_scheduled_scan()
        except Exception as exc:
            logger.error("Scheduler tick failed: %s", exc)

        # Wait for the interval or shutdown
        try:
            await asyncio.wait_for(
                _shutdown_event.wait(),
                timeout=interval,
            )
            break  # Shutdown was triggered
        except asyncio.TimeoutError:
            pass  # Timeout expired → next tick


async def _run_scheduled_scan() -> None:
    """Execute one scheduled scan cycle."""
    from app.db.mongodb import get_database
    from app.services.auto_detect_service import create_detection_job, run_detection_job
    from app.services.task_queue import task_queue

    db = get_database()

    # Find users who have at least one completed asset
    pipeline = [
        {"$match": {"status": "completed", "fingerprint": {"$ne": None}}},
        {"$group": {"_id": "$user_id"}},
        {"$limit": 50},  # Process max 50 users per tick
    ]

    user_ids = []
    async for doc in db["assets"].aggregate(pipeline):
        user_ids.append(doc["_id"])

    if not user_ids:
        logger.debug("Scheduler: no users with completed assets — skipping.")
        return

    logger.info("Scheduler: found %d users with assets — creating scan jobs.", len(user_ids))

    for uid in user_ids:
        try:
            # For now, run a general YouTube scan with the user's asset names
            # In production, users would configure their scan keywords
            asset_doc = await db["assets"].find_one(
                {"user_id": uid, "status": "completed"},
                {"filename": 1},
            )
            keyword = asset_doc.get("filename", "digital art") if asset_doc else "digital art"
            # Clean the keyword (remove extension)
            keyword = keyword.rsplit(".", 1)[0] if "." in keyword else keyword

            job_id = await create_detection_job(
                user_id=uid,
                source="youtube",
                query=keyword,
            )

            # Dispatch to TaskQueue
            task_id = task_queue.enqueue(
                run_detection_job,
                job_id=job_id,
                task_name=f"auto_detect_{job_id[:8]}",
                max_retries=1,
                timeout_sec=float(settings.AUTO_SCAN_TIMEOUT_SEC),
            )
            await db["detection_jobs"].update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {
                    "queue_task_id": task_id,
                    "status": "pending",
                    "retries": 0,
                    "max_retries": 1,
                    "queued_at": datetime.now(timezone.utc),
                }},
            )

            logger.info(
                "Scheduler: dispatched job %s for user=%s query='%s'",
                job_id, uid, keyword,
            )

        except Exception as exc:
            logger.warning("Scheduler: failed to create job for user=%s: %s", uid, exc)


def start_scheduler() -> None:
    """Start the background scheduler (call from lifespan startup)."""
    global _scheduler_task, _shutdown_event

    # Only start if YouTube API key is configured
    if not settings.YOUTUBE_API_KEY:
        logger.info(
            "Auto-detection scheduler NOT started — YOUTUBE_API_KEY not configured. "
            "Manual scans via API are still available."
        )
        return

    _shutdown_event = asyncio.Event()
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("Auto-detection scheduler task created.")


async def stop_scheduler() -> None:
    """Stop the background scheduler gracefully (call from lifespan shutdown)."""
    global _scheduler_task

    if _scheduler_task is None:
        return

    _shutdown_event.set()

    try:
        await asyncio.wait_for(_scheduler_task, timeout=10.0)
    except asyncio.TimeoutError:
        _scheduler_task.cancel()
        logger.warning("Scheduler task cancelled after timeout.")
    except asyncio.CancelledError:
        pass

    _scheduler_task = None
    logger.info("Auto-detection scheduler stopped.")
