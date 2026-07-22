import time
from collections import defaultdict, deque


class SlidingWindow:
    """In-memory per-key sliding-window counter. Single-process by design
    (the backend runs as one uvicorn worker); restart resets the windows,
    which is acceptable for abuse throttling."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        events = self._events[key]
        while events and now - events[0] > window_seconds:
            events.popleft()
        if len(events) >= limit:
            return False
        events.append(now)
        return True


limiter = SlidingWindow()
