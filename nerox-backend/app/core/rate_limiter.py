"""
app/core/rate_limiter.py
========================
In-memory sliding-window rate limiter.

Algorithm
---------
Each unique key (e.g. user_id) maps to a deque of monotonic timestamps.
On every check:
  1. Expired timestamps (older than the window) are discarded.
  2. If the remaining count >= max_calls → deny and return False.
  3. Otherwise, append the current timestamp and return True.

Thread Safety
-------------
A threading.Lock guards all deque mutations so the limiter is safe under
FastAPI's default single-process threadpool.

Limitations
-----------
State is per-process. In a multi-worker / Kubernetes deployment the limit
is per-pod, not global.  Replace with a Redis-backed implementation for
distributed rate limiting.

Module-level singletons
-----------------------
  upload_rate_limiter  — 10 uploads / 60 seconds per user
"""

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter keyed by arbitrary string identifiers."""

    def __init__(self, max_calls: int, window_seconds: float) -> None:
        """
        Args:
            max_calls:       Max allowed calls within the window.
            window_seconds:  Duration of the sliding window in seconds.
        """
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._timestamps: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

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
upload_rate_limiter = SlidingWindowRateLimiter(max_calls=10, window_seconds=60)
