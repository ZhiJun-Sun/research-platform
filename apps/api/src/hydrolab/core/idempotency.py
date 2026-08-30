"""创建命令的幂等键支持（plans/02 第 5.4 节）。

当前为进程内实现；接入 PostgreSQL 后替换为数据库唯一约束实现，
语义不变：同一 (scope, key) 只执行一次，重复请求返回首次结果。
"""

from typing import Any


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], Any] = {}

    def get(self, scope: str, key: str) -> Any | None:
        return self._records.get((scope, key))

    def put(self, scope: str, key: str, value: Any) -> None:
        self._records.setdefault((scope, key), value)
