"""Run 执行器端口（plans/05 第 3、15 节）。

实现：FakeRunExecutor → DockerGpuRunExecutor。
规则：API 进程不持有 Docker 权限；GPU 租约由 HydroLab 管理。
"""

from typing import Protocol

from hydrolab.ports.dto import RunHandle, RunSpec, RunStatusSnapshot


class RunExecutor(Protocol):
    async def start(self, spec: RunSpec) -> RunHandle: ...

    async def status(self, handle: RunHandle) -> RunStatusSnapshot: ...

    async def cancel(self, handle: RunHandle) -> None: ...

    async def healthcheck(self) -> bool: ...
