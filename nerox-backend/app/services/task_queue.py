"""
Compatibility facade for distributed Redis/RQ task queue.
"""

from app.worker.redis_queue import RedisTaskQueue

task_queue = RedisTaskQueue()
