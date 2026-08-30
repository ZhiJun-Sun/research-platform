"""Fake RunExecutor：验证状态机、取消、幂等与重复启动防护。"""

from hydrolab.adapters.fake.base import FailureInjector
from hydrolab.core.errors import conflict, not_found, validation_error
from hydrolab.ports.dto import RunHandle, RunSpec, RunState, RunStatusSnapshot


class FakeRunExecutor:
    def __init__(self) -> None:
        self.injector = FailureInjector()
        self._runs: dict[str, RunStatusSnapshot] = {}
        self.started_specs: dict[str, RunSpec] = {}

    async def start(self, spec: RunSpec) -> RunHandle:
        self.injector._record("start", spec)
        if not spec.argv:
            raise validation_error("RunSpec.argv 不能为空")
        if not spec.image_digest:
            raise validation_error("RunSpec.image_digest 不能为空")
        external_id = f"fake-exec-{spec.run_id.hex[:12]}"
        if external_id in self._runs:
            raise conflict("Run 已在执行", {"run_id": str(spec.run_id)})
        self._runs[external_id] = RunStatusSnapshot(
            run_id=spec.run_id, state=RunState.RUNNING
        )
        self.started_specs[external_id] = spec
        return RunHandle(run_id=spec.run_id, external_id=external_id, state=RunState.RUNNING)

    async def status(self, handle: RunHandle) -> RunStatusSnapshot:
        self.injector._record("status", handle)
        snapshot = self._runs.get(handle.external_id)
        if snapshot is None:
            raise not_found("执行实例不存在")
        return snapshot

    async def cancel(self, handle: RunHandle) -> None:
        self.injector._record("cancel", handle)
        snapshot = self._runs.get(handle.external_id)
        if snapshot is None:
            raise not_found("执行实例不存在")
        if snapshot.state in (RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED):
            return  # 取消天然幂等
        snapshot.state = RunState.CANCELLED

    async def healthcheck(self) -> bool:
        self.injector._record("healthcheck")
        return True

    # --- 测试辅助：驱动状态机 ---
    def complete(self, external_id: str, exit_code: int = 0) -> None:
        snapshot = self._runs[external_id]
        snapshot.state = RunState.SUCCEEDED if exit_code == 0 else RunState.FAILED
        snapshot.exit_code = exit_code

    def fail(self, external_id: str, message: str) -> None:
        snapshot = self._runs[external_id]
        snapshot.state = RunState.FAILED
        snapshot.message = message
