import time
from collections import defaultdict


class RateLimiter:
    """Fixed-window limiter. In-process only: with several API replicas the effective limit multiplies."""

    def __init__(self, limit: int, window: float = 60.0, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = self.clock()
        hits = [t for t in self._hits[key] if now - t < self.window]
        if len(hits) >= self.limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True


class SharedRateLimiter:
    """Fixed-window limiter whose counters live in PostgreSQL, so every API replica shares one budget.

    `engine` is a SQLAlchemy engine. Keys are hashed before storage (no e-mail addresses or IPs at rest).
    If the database call fails the limiter degrades to a per-process limiter instead of failing open or locking
    everyone out; the degradation is logged."""

    UPSERT = ("INSERT INTO rate_limits(key, window_start, hits) VALUES (:k, :w, 1) "
              "ON CONFLICT (key, window_start) DO UPDATE SET hits = rate_limits.hits + 1 RETURNING hits")

    def __init__(self, engine, name: str, limit: int, window: float = 60.0, clock=time.time):
        self.e, self.name, self.limit, self.window, self.clock = engine, name, limit, int(window), clock
        self._fallback = RateLimiter(limit, window)
        self._last_purge = 0.0

    def allow(self, key: str) -> bool:
        import hashlib
        import logging

        from sqlalchemy import text
        now = self.clock()
        w = int(now // self.window)
        k = hashlib.sha256(f"{self.name}:{key}".encode()).hexdigest()
        try:
            with self.e.begin() as c:
                hits = c.execute(text(self.UPSERT), dict(k=k, w=w)).scalar_one()
                if now - self._last_purge > self.window:  # old windows are useless: drop them now and then
                    c.execute(text("DELETE FROM rate_limits WHERE window_start < :w"), dict(w=w - 1))
                    self._last_purge = now
            return hits <= self.limit
        except Exception:  # noqa: BLE001
            logging.getLogger("novacloud.ratelimit").warning("shared rate limiter unavailable; using per-process fallback")
            return self._fallback.allow(f"{self.name}:{key}")
