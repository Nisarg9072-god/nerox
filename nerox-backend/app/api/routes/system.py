from __future__ import annotations

from fastapi import APIRouter

from app.services.task_queue import task_queue

router = APIRouter()


@router.get("/metrics", summary="Distributed queue and worker metrics")
async def system_metrics() -> dict:
    return task_queue.metrics()

