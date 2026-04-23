"""
app/services/task_queue.py
===========================
Production-grade background task system for Nerox.

Phase 2 replacement for FastAPI BackgroundTasks — provides:
  • asyncio-native task dispatch (non-blocking)
  • ThreadPoolExecutor for CPU-bound work (fingerprinting, watermarking)
  • Automatic retry on failure (configurable max_retries)
  • Per-task status tracking: pending → processing → completed / failed
  • Error logging with full tracebacks
  • Graceful shutdown (waits for running tasks, cancels pending)

Usage from route handlers::

    from app.services.task_queue import task_queue

    task_queue.enqueue(
        process_fingerprint,
        fingerprint_id=fp_id,
        asset_id=asset_id,
        file_path=path,
        file_type=ftype,
        task_name="fingerprint",
        max_retries=2,
    )
"""

from __future__ import annotations

import asyncio
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

from app.core.logger import get_logger

logger = get_logger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskRecord:
    """Tracks the lifecycle of a background task."""
    task_id: str
    task_name: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retries: int = 0
    max_retries: int = 2


class TaskQueue:
    """
    Async task queue with retry support and thread-pool offloading.

    Designed to run within the FastAPI event loop — all dispatched tasks
    execute as ``asyncio.Task`` objects and are tracked in-memory.
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, TaskRecord] = {}
        self._running: set[asyncio.Task] = set()
        self._shutdown = False

    def enqueue(
        self,
        fn: Callable,
        *,
        task_name: str = "unnamed",
        max_retries: int = 2,
        **kwargs: Any,
    ) -> str:
        """
        Enqueue a coroutine or sync function for background execution.

        Args:
            fn: The async or sync function to execute.
            task_name: Human-readable name for logging / status tracking.
            max_retries: Number of automatic retries on failure.
            **kwargs: Arguments passed to ``fn``.

        Returns:
            task_id string for status queries.
        """
        if self._shutdown:
            raise RuntimeError("TaskQueue is shutting down — cannot enqueue new tasks.")

        task_id = str(uuid4())
        record = TaskRecord(
            task_id=task_id,
            task_name=task_name,
            max_retries=max_retries,
        )
        self._tasks[task_id] = record

        # Schedule on the event loop
        aio_task = asyncio.create_task(
            self._execute(record, fn, kwargs)
        )
        self._running.add(aio_task)
        aio_task.add_done_callback(self._running.discard)

        logger.info(
            "Task enqueued — id=%s name=%s retries=%d",
            task_id, task_name, max_retries,
        )
        return task_id

    async def _execute(
        self,
        record: TaskRecord,
        fn: Callable,
        kwargs: dict[str, Any],
    ) -> None:
        """Execute the task with retry logic."""
        for attempt in range(record.max_retries + 1):
            record.status = TaskStatus.PROCESSING
            record.started_at = datetime.now(timezone.utc)
            record.retries = attempt

            try:
                if asyncio.iscoroutinefunction(fn):
                    await fn(**kwargs)
                else:
                    # Run sync functions in thread pool
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(self._executor, lambda: fn(**kwargs))

                record.status = TaskStatus.COMPLETED
                record.completed_at = datetime.now(timezone.utc)
                record.error_message = None
                logger.info(
                    "Task completed — id=%s name=%s attempt=%d",
                    record.task_id, record.task_name, attempt + 1,
                )
                return

            except Exception as exc:
                record.error_message = f"{exc}\n{traceback.format_exc()}"
                logger.error(
                    "Task failed — id=%s name=%s attempt=%d/%d: %s",
                    record.task_id, record.task_name,
                    attempt + 1, record.max_retries + 1, exc,
                )

                if attempt < record.max_retries:
                    # Exponential backoff: 2s, 4s, 8s...
                    wait = 2 ** (attempt + 1)
                    logger.info(
                        "Retrying task %s in %ds...", record.task_id, wait,
                    )
                    await asyncio.sleep(wait)

        # All retries exhausted
        record.status = TaskStatus.FAILED
        record.completed_at = datetime.now(timezone.utc)
        logger.error(
            "Task permanently FAILED — id=%s name=%s after %d attempts",
            record.task_id, record.task_name, record.max_retries + 1,
        )

    def get_status(self, task_id: str) -> Optional[TaskRecord]:
        """Return the status record for a given task_id, or None."""
        return self._tasks.get(task_id)

    async def shutdown(self, timeout: float = 30.0) -> None:
        """
        Graceful shutdown: wait for all running tasks to complete (up to timeout).
        """
        self._shutdown = True
        if self._running:
            logger.info("TaskQueue: waiting for %d running tasks...", len(self._running))
            done, pending = await asyncio.wait(
                self._running, timeout=timeout
            )
            for task in pending:
                task.cancel()
            if pending:
                logger.warning(
                    "TaskQueue: cancelled %d tasks after %.1fs timeout",
                    len(pending), timeout,
                )
        self._executor.shutdown(wait=False)
        logger.info("TaskQueue shut down.")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
task_queue = TaskQueue(max_workers=4)
