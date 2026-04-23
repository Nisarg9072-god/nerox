"""Redis-backed distributed rate limiter with in-memory fallback."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

import redis

from app.core.config import settings


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter keyed by arbitrary string identifiers."""

    def __init__(self, max_calls: int, window_seconds: float, scope: str) -> None:
        """
        Args:
            max_calls:       Max allowed calls within the window.
            window_seconds:  Duration of the sliding window in seconds.
        """
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.scope = scope
        self._timestamps: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        try:
            self._redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            self._redis.ping()
        except Exception:
            self._redis = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_allowed(self, key: str) -> bool:
        """
        Check whether a new request is within the rate limit.

        Consumes one slot if allowed (side-effecting).

        Args:
            key: Unique identifier for the caller (e.g. user_id string).

        Returns:
            True  — request is allowed.
            False — rate limit exceeded; caller should return HTTP 429.
        """
        if self._redis:
            return self._is_allowed_redis(key)
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            ts = self._timestamps[key]

            # Evict expired timestamps
            while ts and ts[0] < cutoff:
                ts.popleft()

            if len(ts) >= self.max_calls:
                return False

            ts.append(now)
            return True

    def _is_allowed_redis(self, key: str) -> bool:
        assert self._redis is not None
        redis_key = f"{settings.RATE_LIMIT_REDIS_PREFIX}:{self.scope}:{key}"
        current = self._redis.incr(redis_key)
        if current == 1:
            self._redis.expire(redis_key, int(self.window_seconds))
        return current <= self.max_calls

    def remaining(self, key: str) -> int:
        """
        How many calls this key may still make in the current window.

        Does NOT consume a slot (read-only).
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            ts = self._timestamps[key]
            while ts and ts[0] < cutoff:
                ts.popleft()
            return max(0, self.max_calls - len(ts))

    def reset(self, key: str) -> None:
        """Clear all recorded timestamps for a key (useful in tests)."""
        with self._lock:
            self._timestamps.pop(key, None)


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

#: 10 uploads per 60-second window per user
upload_rate_limiter = SlidingWindowRateLimiter(max_calls=10, window_seconds=60, scope="upload")
login_rate_limiter = SlidingWindowRateLimiter(max_calls=8, window_seconds=60, scope="login")
detect_rate_limiter = SlidingWindowRateLimiter(max_calls=30, window_seconds=60, scope="detect")
