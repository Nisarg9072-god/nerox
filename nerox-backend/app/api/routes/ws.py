"""
app/api/routes/ws.py
======================
Phase 2.6 — WebSocket endpoint for real-time notifications.

Endpoint:
  /ws/notifications?token=<JWT>

Authentication:
  JWT is passed as a query parameter (WebSocket doesn't support
  Authorization headers in the browser). The token is validated
  on connect — invalid tokens are rejected immediately.

Events sent to connected clients:
  - detection_found   → New similarity match detected
  - alert_created     → New alert triggered
  - job_progress      → Detection job progress update
  - job_completed     → Detection job finished

Clients should reconnect automatically on disconnect (handled
by the frontend WebSocket service).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError

from app.core.logger import get_logger
from app.core.security import decode_access_token
from app.services.ws_manager import ws_manager

logger = get_logger(__name__)

router = APIRouter()


@router.websocket("/notifications")
async def websocket_notifications(
    websocket: WebSocket,
    token: str = Query(default=""),
) -> None:
    """
    WebSocket endpoint for real-time notifications.

    Authentication via JWT query parameter:
      ws://host/ws/notifications?token=<jwt>

    On connect:
      1. Validate JWT token
      2. Extract user_id from token payload
      3. Register connection with WebSocketManager

    While connected:
      - Server pushes events as JSON messages
      - Client can send pings (keepalive)

    On disconnect:
      - Connection is removed from manager
    """
    # ── Authenticate ────────────────────────────────────────────────────────
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise JWTError("Missing subject claim")
    except JWTError as exc:
        logger.warning("WS auth failed: %s", exc)
        await websocket.close(code=4003, reason="Invalid or expired token")
        return

    # ── Connect ─────────────────────────────────────────────────────────────
    await ws_manager.connect(user_id, websocket)

    try:
        # Send initial connected confirmation
        await websocket.send_text(json.dumps({
            "type": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "message": "Real-time notifications active",
                "user_id": user_id,
            },
        }))

        # Keep alive — listen for client pings
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0,  # 60s keepalive timeout
                )
                # Handle ping
                if data == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": {},
                    }))
            except asyncio.TimeoutError:
                # Send server-side keepalive
                try:
                    await websocket.send_text(json.dumps({
                        "type": "ping",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": {},
                    }))
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WS error for user=%s: %s", user_id, exc)
    finally:
        await ws_manager.disconnect(user_id, websocket)
