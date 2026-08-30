"""公开端点的简单限流（固定窗口计数）。

用于 /shared/{token} 等防枚举场景；生产可替换为 Redis 实现，
窗口语义不变。超限时抛 RATE_LIMITED。
"""

import time
from collections import defaultdict

from hydrolab.core.errors import AppError


class FixedWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window = window_seconds
        self._counters: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))

    def check(self, key: str) -> None:
        now = time.monotonic()
        count, window_start = self._counters[key]
        if now - window_start >= self._window:
            count, window_start = 0, now
        count += 1
        self._counters[key] = (count, window_start)
        if count > self._limit:
            raise AppError("RATE_LIMITED", "请求过于频繁，请稍后再试", status_code=429)
