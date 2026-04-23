from __future__ import annotations

import os
import asyncio

from redis import Redis
from rq import Queue, Worker, SimpleWorker

from app.core.config import settings
from app.core.logger import get_logger
from app.db.mongodb import connect_to_mongo, close_mongo_connection

logger = get_logger(__name__)


def main() -> None:
    asyncio.run(connect_to_mongo())
    redis_conn = Redis.from_url(settings.REDIS_URL)
    queue = Queue(settings.RQ_QUEUE_NAME, connection=redis_conn)

    logger.info(
        "Worker started",
        extra={"event": "worker_start", "queue": settings.RQ_QUEUE_NAME, "redis_url": settings.REDIS_URL},
    )
    worker_cls = SimpleWorker if os.name == "nt" else Worker
    worker_name = f"nerox-worker-{settings.RQ_QUEUE_NAME}-{os.getpid()}"
    worker = worker_cls([queue], connection=redis_conn, name=worker_name)
    try:
        worker.work(with_scheduler=True)
    finally:
        asyncio.run(close_mongo_connection())


if __name__ == "__main__":
    main()

