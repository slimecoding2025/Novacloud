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
