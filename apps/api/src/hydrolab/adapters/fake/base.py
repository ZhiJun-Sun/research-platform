"""Fake 适配器基座：统一的故障/重复注入机制。

契约测试与业务单元测试通过 inject_failure / inject_duplicate
模拟外部系统的失败、超时与重复投递，而不只是 happy path。
"""

from collections.abc import Callable
from typing import Any


class FailureInjector:
    def __init__(self) -> None:
        self._failures: dict[str, list[BaseException]] = {}
        self._duplicates: set[str] = set()
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def inject_failure(self, method: str, exc: BaseException, times: int = 1) -> None:
        self._failures.setdefault(method, []).extend([exc] * times)

    def inject_duplicate(self, method: str) -> None:
        self._duplicates.add(method)

    def _record(self, method: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((method, args, kwargs))
        pending = self._failures.get(method)
        if pending:
            raise pending.pop(0)

    def _should_duplicate(self, method: str) -> bool:
        return method in self._duplicates

    def reset(self) -> None:
        self._failures.clear()
        self._duplicates.clear()
        self.calls.clear()

    def call_count(self, method: str, predicate: Callable[..., bool] | None = None) -> int:
        if predicate is None:
            return sum(1 for name, _, _ in self.calls if name == method)
        return sum(
            1
            for name, args, kwargs in self.calls
            if name == method and predicate(*args, **kwargs)
        )
