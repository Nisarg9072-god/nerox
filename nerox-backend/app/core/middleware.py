from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import Request, Response

from app.core.logger import get_logger

logger = get_logger(__name__)


def request_logging_middleware_factory() -> Callable:
    async def middleware(request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.perf_counter()
        user_id = getattr(request.state, "user_id", None)
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "request_failed",
                extra={
                    "event": "request_failed",
                    "request_id": request_id,
                    "user_id": user_id,
                    "endpoint": request.url.path,
                    "method": request.method,
                    "response_time_ms": elapsed_ms,
                },
            )
            raise

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        logger.info(
            "request_completed",
            extra={
                "event": "request_completed",
                "request_id": request_id,
                "user_id": user_id,
                "endpoint": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "response_time_ms": elapsed_ms,
            },
        )
        return response

    return middleware

