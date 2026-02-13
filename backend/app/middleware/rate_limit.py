"""Rate Limiting Middleware - Token Bucket per client IP"""
import time
from collections import defaultdict
from threading import Lock
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings


class _TokenBucket:
    """Simple token bucket for a single client."""

    __slots__ = ("tokens", "last_refill", "capacity", "refill_rate")

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-IP rate limiting middleware.

    Uses a token-bucket algorithm. Each IP gets *capacity* tokens that refill
    at *capacity / window* tokens per second.  When the bucket is empty the
    request is rejected with 429.
    """

    def __init__(self, app, capacity: int | None = None, window: int | None = None):
        super().__init__(app)
        self.capacity = capacity or settings.RATE_LIMIT_REQUESTS
        self.window = window or settings.RATE_LIMIT_WINDOW_SECONDS
        self.refill_rate = self.capacity / self.window
        self._buckets: dict[str, _TokenBucket] = defaultdict(
            lambda: _TokenBucket(self.capacity, self.refill_rate)
        )
        self._lock = Lock()
        self._last_cleanup = time.monotonic()

    # Paths that should never be rate-limited
    _EXEMPT = frozenset({"/health", "/docs", "/redoc", "/openapi.json"})

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health / docs endpoints
        if request.url.path in self._EXEMPT:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        with self._lock:
            # Periodic cleanup of stale buckets (every 5 minutes)
            now = time.monotonic()
            if now - self._last_cleanup > 300:
                self._cleanup(now)
                self._last_cleanup = now

            bucket = self._buckets[client_ip]
            allowed = bucket.consume()

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后重试"},
            )

        return await call_next(request)

    def _cleanup(self, now: float) -> None:
        """Remove buckets that have been idle for longer than 2× the window."""
        stale_threshold = self.window * 2
        stale = [
            ip
            for ip, b in self._buckets.items()
            if now - b.last_refill > stale_threshold
        ]
        for ip in stale:
            del self._buckets[ip]
