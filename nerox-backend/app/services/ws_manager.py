"""
app/services/ws_manager.py
============================
Phase 2.6 — WebSocket Connection Manager for Real-Time Intelligence.

Manages multiple WebSocket connections per user and provides methods
to broadcast events to specific users or all connected clients.

Event types:
  - detection_found   → New similarity match detected
  - alert_created     → New alert triggered
  - job_progress      → Detection job progress update
  - job_completed     → Detection job finished

Thread safety:
  The manager uses asyncio-safe data structures. All broadcast calls
  are safe to invoke from both async route handlers and sync thread-pool
  workers (via asyncio.run_coroutine_threadsafe).

Usage from anywhere in the app:
    from app.services.ws_manager import ws_manager
    await ws_manager.broadcast_to_user(user_id, {
        "type": "detection_found",
        "asset_id": "...",
        ...
    })
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, Optional, Set
from uuid import uuid4

import redis
from fastapi import WebSocket

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)
WS_EVENTS_CHANNEL = "nerox_ws_events"


class WebSocketManager:
    """
    Manages WebSocket connections grouped by user_id.

    Supports multiple concurrent connections per user (e.g., multiple
    browser tabs). Automatically cleans up on disconnect.
    """

    def __init__(self) -> None:
        # user_id → set of WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self._pending_events: Dict[str, Deque[dict]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._flusher_task: Optional[asyncio.Task] = None
        self._batch_interval_sec = 1.0
        self._max_pending_per_user = 500
        self._sequence_by_user: Dict[str, int] = defaultdict(int)
        self._subscriber_task: Optional[asyncio.Task] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store the primary event loop for thread-safe broadcasts."""
        self._event_loop = loop
        if self._flusher_task is None or self._flusher_task.done():
            self._flusher_task = loop.create_task(self._flush_loop())
        if self._subscriber_task is None or self._subscriber_task.done():
            self._subscriber_task = loop.create_task(self._redis_subscriber_loop())

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections[user_id].add(websocket)

        count = len(self._connections[user_id])
        logger.info(
            "WS connected — user=%s connections=%d",
            user_id, count,
        )

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection on disconnect."""
        async with self._lock:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]
                self._pending_events.pop(user_id, None)
                self._sequence_by_user.pop(user_id, None)

        logger.info("WS disconnected — user=%s", user_id)

    async def broadcast_to_user(self, user_id: str, data: dict) -> None:
        """
        Send a JSON message to ALL connections for a specific user.

        Silently removes dead connections.
        """
        connections = self._connections.get(user_id, set()).copy()
        if not connections:
            return

        payload = json.dumps(data, default=str)
        dead: list[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        # Clean up dead connections
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections[user_id].discard(ws)
                if not self._connections[user_id]:
                    del self._connections[user_id]
                    self._pending_events.pop(user_id, None)

    async def _flush_loop(self) -> None:
        """Batch flush pending events to clients every interval."""
        while True:
            try:
                await asyncio.sleep(self._batch_interval_sec)
                await self.flush_pending()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("WS flush loop error: %s", exc)

    async def _redis_subscriber_loop(self) -> None:
        """Subscribe to Redis-published WS events from worker processes."""
        try:
            client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            pubsub = client.pubsub()
            pubsub.subscribe(WS_EVENTS_CHANNEL)
        except Exception as exc:
            logger.warning("WS Redis subscriber unavailable: %s", exc)
            return

        while True:
            try:
                msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("data"):
                    payload = json.loads(msg["data"])
                    if payload.get("event_type") == "fingerprint_completed":
                        try:
                            from app.services.vector_service import get_vector_index
                            await asyncio.to_thread(get_vector_index().load_from_db)
                        except Exception as exc:
                            logger.debug("FAISS reload after fingerprint event failed: %s", exc)
                    await self.enqueue_event(
                        user_id=payload["user_id"],
                        event_type=payload["event_type"],
                        data=payload.get("data", {}),
                    )
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("WS Redis subscriber error: %s", exc)

    async def flush_pending(self) -> None:
        """Flush all pending event queues as batched WS payloads."""
        users = list(self._pending_events.keys())
        ts = datetime.now(timezone.utc).isoformat()
        for user_id in users:
            queue = self._pending_events.get(user_id)
            if not queue:
                continue
            events = []
            while queue:
                events.append(queue.popleft())
            if not events:
                continue
            events.sort(key=lambda e: int(e.get("sequence", 0)))
            logger.debug("WS batch emitted user=%s size=%d", user_id, len(events))
            await self.broadcast_to_user(user_id, {
                "type": "batch",
                "timestamp": ts,
                "data": {"events": events, "count": len(events)},
            })

    async def enqueue_event(self, user_id: str, event_type: str, data: dict) -> None:
        """Enqueue standardized event for next batch flush."""
        self._sequence_by_user[user_id] += 1
        seq = self._sequence_by_user[user_id]
        evt = {
            "event_id": f"{user_id}:{seq}:{uuid4().hex[:10]}",
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sequence": seq,
            "data": data,
        }
        queue = self._pending_events[user_id]
        if len(queue) >= self._max_pending_per_user:
            queue.popleft()
            logger.warning("WS queue overflow user=%s dropped_oldest=1", user_id)
        queue.append(evt)
        logger.debug("WS event queued user=%s type=%s", user_id, event_type)

    async def broadcast_to_all(self, data: dict) -> None:
        """Send a JSON message to ALL connected users."""
        user_ids = list(self._connections.keys())
        for uid in user_ids:
            await self.broadcast_to_user(uid, data)

    @property
    def connected_users(self) -> int:
        """Number of users with at least one active connection."""
        return len(self._connections)

    @property
    def total_connections(self) -> int:
        """Total number of active WebSocket connections."""
        return sum(len(conns) for conns in self._connections.values())


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
ws_manager = WebSocketManager()


# ---------------------------------------------------------------------------
# Helper: fire-and-forget broadcast from sync context (thread pool)
# ---------------------------------------------------------------------------

def enqueue_event_sync(user_id: str, event_type: str, data: dict) -> None:
    """
    Broadcast a WebSocket event from a synchronous context (e.g., thread pool).

    Uses asyncio.run_coroutine_threadsafe to safely schedule the coroutine
    on the main event loop. Non-blocking, non-fatal.
    """
    try:
        loop = ws_manager._event_loop
        if loop is None:
            _publish_event_to_redis(user_id=user_id, event_type=event_type, data=data)
            return
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                ws_manager.enqueue_event(user_id, event_type, data),
                loop,
            )
        else:
            _publish_event_to_redis(user_id=user_id, event_type=event_type, data=data)
    except Exception as exc:
        logger.debug("WS enqueue_event_sync failed (non-fatal): %s", exc)


def _publish_event_to_redis(user_id: str, event_type: str, data: dict) -> None:
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.publish(WS_EVENTS_CHANNEL, json.dumps({
            "user_id": user_id,
            "event_type": event_type,
            "data": data,
        }, default=str))
    except Exception as exc:
        logger.debug("WS Redis publish failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Convenience event constructors
# ---------------------------------------------------------------------------

def emit_detection_found(
    user_id: str,
    asset_id: str,
    similarity: float,
    source: str,
    source_url: str,
    platform: str,
    detection: Optional[dict] = None,
) -> None:
    """Emit a detection_found event to the user's WebSocket connections."""
    enqueue_event_sync(user_id, "detection_found", {
        "asset_id": asset_id,
        "similarity": round(similarity, 4),
        "source": source,
        "url": source_url,
        "platform": platform,
        "detection": detection or {},
    })


def emit_alert_created(
    user_id: str,
    alert_type: str,
    severity: str,
    asset_id: str,
    message: str,
    alert: Optional[dict] = None,
) -> None:
    """Emit an alert_created event to the user's WebSocket connections."""
    enqueue_event_sync(user_id, "alert_created", {
        "alert_type": alert_type,
        "severity": severity,
        "asset_id": asset_id,
        "message": message,
        "alert": alert or {},
    })


def emit_job_progress(
    user_id: str,
    job_id: str,
    total_scanned: int,
    matches_found: int,
    status: str = "running",
) -> None:
    """Emit a job_progress event to the user's WebSocket connections."""
    enqueue_event_sync(user_id, "job_progress", {
        "job_id": job_id,
        "status": status,
        "total_scanned": total_scanned,
        "matches_found": matches_found,
    })


def emit_job_completed(
    user_id: str,
    job_id: str,
    total_scanned: int,
    matches_found: int,
    status: str = "completed",
    top_matches: Optional[list[dict]] = None,
    alerts: Optional[list[dict]] = None,
) -> None:
    """Emit a job_completed event to the user's WebSocket connections."""
    enqueue_event_sync(user_id, "job_completed", {
        "job_id": job_id,
        "status": status,
        "total_scanned": total_scanned,
        "matches_found": matches_found,
        "top_matches": top_matches or [],
        "alerts": alerts or [],
    })


def emit_job_failed(
    user_id: str,
    job_id: str,
    reason: str,
    total_scanned: int = 0,
    matches_found: int = 0,
) -> None:
    """Emit explicit job_failed event for failure visibility."""
    enqueue_event_sync(user_id, "job_failed", {
        "job_id": job_id,
        "reason": reason,
        "status": "failed",
        "total_scanned": total_scanned,
        "matches_found": matches_found,
    })


def emit_fingerprint_completed(user_id: str, asset_id: str, fingerprint_id: str) -> None:
    """Emit fingerprint completion event for live asset status updates."""
    enqueue_event_sync(user_id, "fingerprint_completed", {
        "asset_id": asset_id,
        "fingerprint_id": fingerprint_id,
        "status": "completed",
    })


def emit_fingerprint_failed(user_id: str, asset_id: str, fingerprint_id: str, reason: str) -> None:
    """Emit fingerprint failure event for live asset status updates."""
    enqueue_event_sync(user_id, "fingerprint_failed", {
        "asset_id": asset_id,
        "fingerprint_id": fingerprint_id,
        "status": "failed",
        "reason": reason,
    })


def emit_watermark_completed(user_id: str, asset_id: str, watermark_id: str) -> None:
    """Emit watermark completion event for live asset status updates."""
    enqueue_event_sync(user_id, "watermark_completed", {
        "asset_id": asset_id,
        "watermark_id": watermark_id,
        "status": "completed",
    })


def emit_watermark_failed(user_id: str, asset_id: str, watermark_id: str, reason: str) -> None:
    """Emit watermark failure event for live asset status updates."""
    enqueue_event_sync(user_id, "watermark_failed", {
        "asset_id": asset_id,
        "watermark_id": watermark_id,
        "status": "failed",
        "reason": reason,
    })


def emit_watermark_verified(
    user_id: str,
    asset_id: str,
    watermark_id: str,
    confidence: float,
    confidence_label: str,
) -> None:
    """Emit explicit watermark_verified event after successful verification."""
    enqueue_event_sync(user_id, "watermark_verified", {
        "asset_id": asset_id,
        "watermark_id": watermark_id,
        "status": "verified",
        "confidence": round(float(confidence), 4),
        "confidence_label": confidence_label,
    })
