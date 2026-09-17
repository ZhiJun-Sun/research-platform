"""DockerGpuRunExecutor 单测（Runner 安全 Spike 验证）。

本地无 Docker daemon，mock docker client 验证适配器的编排逻辑与安全基线：
镜像白名单校验、argv 直传（无 shell）、非 root、禁网、GPU 申请、重复启动防护、
取消幂等、健康检查降级。
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from hydrolab.adapters.docker import DockerGpuRunExecutor
from hydrolab.core.errors import AppError
from hydrolab.ports.dto import RunSpec, RunState

_IMAGE = "sha256:" + "a" * 64


def _spec(**overrides) -> RunSpec:
    base = dict(
        run_id=uuid4(),
        argv=["python", "train.py"],
        image_digest=_IMAGE,
        gpu_count=1,
    )
    base.update(overrides)
    return RunSpec(**base)


def _mock_docker_client() -> MagicMock:
    client = MagicMock()
    container = MagicMock()
    container.id = "container-123"
    client.containers.run = MagicMock(return_value=container)
    client.ping = MagicMock(return_value=True)
    return client


@pytest.fixture()
def executor() -> DockerGpuRunExecutor:
    return DockerGpuRunExecutor(
        image_whitelist=[_IMAGE],
        docker_client=_mock_docker_client(),
    )


async def test_start_creates_container_non_root_no_shell(executor: DockerGpuRunExecutor) -> None:
    handle = await executor.start(_spec())
    assert handle.external_id.startswith("docker-")
    client = executor._client
    client.containers.run.assert_called_once()
    kwargs = client.containers.run.call_args.kwargs
    # argv 直传（command 为列表，非 shell 字符串）
    assert isinstance(kwargs["command"], list)
    # 非 root + 禁网 + GPU 申请
    assert kwargs["user"] == "65534:65534"
    assert kwargs["network_disabled"] is True
    assert kwargs["device_requests"] and kwargs["device_requests"][0]["Driver"] == "nvidia"


async def test_start_binds_workspace_and_exact_gpu_ids(executor: DockerGpuRunExecutor, tmp_path) -> None:
    code_dir = tmp_path / "code"
    output_dir = tmp_path / "output"
    code_dir.mkdir()
    output_dir.mkdir()

    await executor.start(
        _spec(read_only_mounts=[str(code_dir)], writable_mount=str(output_dir), gpu_indices=[2])
    )
    kwargs = executor._client.containers.run.call_args.kwargs
    assert kwargs["volumes"] == {
        str(code_dir.resolve()): {"bind": "/workspace/code", "mode": "ro"},
        str(output_dir.resolve()): {"bind": "/workspace/output", "mode": "rw"},
    }
    assert kwargs["device_requests"][0]["DeviceIDs"] == ["2"]
    assert "Count" not in kwargs["device_requests"][0]
    assert kwargs["environment"]["CUDA_VISIBLE_DEVICES"] == "0"
    assert kwargs["environment"]["HYDROLAB_OUTPUT_DIR"] == "/workspace/output"


async def test_zero_timeout_polls_without_wait_or_removal(executor):
    handle = await executor.start(_spec())
    container = executor._client.containers.get.return_value
    container.attrs = {"State": {"Running": True}}
    assert (await executor.wait(handle.external_id, timeout=0)).state == RunState.RUNNING
    container.wait.assert_not_called()
    container.remove.assert_not_called()
    assert handle.external_id in executor._container_ids
    container.attrs = {"State": {"Running": False, "ExitCode": 0}}
    assert (await executor.wait(handle.external_id, timeout=0)).state == RunState.SUCCEEDED
    container.remove.assert_not_called()
    await executor.cleanup(handle.external_id)
    container.remove.assert_called_once_with(force=True)


async def test_cancel_failure_does_not_report_success(executor):
    handle = await executor.start(_spec())
    executor._client.containers.get.side_effect = ConnectionError("daemon unreachable")
    with pytest.raises(ConnectionError):
        await executor.cancel(handle)
    assert (await executor.status(handle)).state == RunState.RUNNING


async def test_argv_python_resolved_to_container_python() -> None:
    executor = DockerGpuRunExecutor(
        image_whitelist=[_IMAGE],
        docker_client=_mock_docker_client(),
        container_python="/opt/venv/bin/python",
    )
    await executor.start(_spec(argv=["python", "train.py"]))
    command = executor._client.containers.run.call_args.kwargs["command"]
    assert command[0] == "/opt/venv/bin/python"


async def test_non_whitelisted_image_rejected() -> None:
    executor = DockerGpuRunExecutor(
        image_whitelist=["sha256:" + "b" * 64],
        docker_client=_mock_docker_client(),
    )
    with pytest.raises(AppError):
        await executor.start(_spec())  # 用 whitelist 外镜像


async def test_duplicate_start_conflicts(executor: DockerGpuRunExecutor) -> None:
    spec = _spec()
    await executor.start(spec)
    with pytest.raises(AppError) as exc:
        await executor.start(spec)
    assert exc.value.code == "CONFLICT"


async def test_cancel_is_idempotent(executor: DockerGpuRunExecutor) -> None:
    handle = await executor.start(_spec())
    await executor.cancel(handle)
    assert (await executor.status(handle)).state == RunState.CANCELLED
    await executor.cancel(handle)  # 重复取消不报错


async def test_healthcheck_ok(executor: DockerGpuRunExecutor) -> None:
    assert await executor.healthcheck() is True


async def test_healthcheck_false_when_daemon_down() -> None:
    client = MagicMock()
    client.ping = MagicMock(side_effect=RuntimeError("daemon down"))
    executor = DockerGpuRunExecutor(
        image_whitelist=[_IMAGE], docker_client=client
    )
    assert await executor.healthcheck() is False


async def test_nvidia_runtime_mode_uses_runtime_flag_and_visible_devices() -> None:
    """CDI 模式宿主机：runtime=nvidia + NVIDIA_VISIBLE_DEVICES，不用 device_requests。"""
    executor = DockerGpuRunExecutor(
        image_whitelist=[_IMAGE],
        docker_client=_mock_docker_client(),
        gpu_mode="nvidia_runtime",
    )
    await executor.start(_spec(gpu_indices=[2], gpu_count=1))
    kwargs = executor._client.containers.run.call_args.kwargs
    assert kwargs["runtime"] == "nvidia"
    assert kwargs["environment"]["NVIDIA_VISIBLE_DEVICES"] == "2"
    assert kwargs["environment"]["CUDA_VISIBLE_DEVICES"] == "0"
    assert kwargs["device_requests"] == []


async def test_none_mode_skips_gpu_injection() -> None:
    executor = DockerGpuRunExecutor(
        image_whitelist=[_IMAGE], docker_client=_mock_docker_client(), gpu_mode="none"
    )
    await executor.start(_spec())
    kwargs = executor._client.containers.run.call_args.kwargs
    assert kwargs["device_requests"] == []
    assert "runtime" not in kwargs
    assert "CUDA_VISIBLE_DEVICES" not in kwargs["environment"]
    assert "NVIDIA_VISIBLE_DEVICES" not in kwargs["environment"]


def test_unknown_gpu_mode_rejected() -> None:
    with pytest.raises(AppError):
        DockerGpuRunExecutor(image_whitelist=[_IMAGE], docker_client=_mock_docker_client(), gpu_mode="bogus")


async def test_empty_argv_rejected(executor: DockerGpuRunExecutor) -> None:
    with pytest.raises(AppError):
        await executor.start(_spec(argv=[]))
