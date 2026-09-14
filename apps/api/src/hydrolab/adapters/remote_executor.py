"""API-side marker: Docker access belongs exclusively to the Worker."""

from hydrolab.core.errors import conflict


class RemoteRunExecutor:
    real_executor = False
    remote_executor = True

    async def start(self, spec):
        raise conflict("训练由独立 Worker 执行")

    async def status(self, handle):
        raise conflict("请从数据库读取 Run 状态")

    async def cancel(self, handle):
        raise conflict("取消必须通过 Worker 队列")

    async def healthcheck(self) -> bool:
        # No Docker probe in the API. Worker readiness is a separate gate.
        return True
