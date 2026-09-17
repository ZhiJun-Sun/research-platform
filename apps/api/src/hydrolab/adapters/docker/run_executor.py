"""Docker GPU RunExecutor 真实实现（Runner 安全 Spike 适配器）。

安全基线（plans/05 §7 / §15 Runner 安全 Spike）：
- 仅允许白名单镜像（digest 固定），非白名单拒绝；
- argv 直传 exec，从不经过 shell，避免命令注入；
- 容器非 root、工作目录只读挂载、默认禁用网络（按配置放开）；
- GPU 注入按 gpu_mode：device_requests（--gpus 等价，默认）或 nvidia_runtime
  （CDI 模式宿主机，经 nvidia container runtime 注入）；none 不注入。

实现形态：本文件实现 RunExecutor 端口，可用注入的 mock client 单测；
真实部署建议把容器生命周期交给独立 Runner Controller（apps/runner），
API 只投递 RunSpec，避免 API 进程直接持有 Docker socket。
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import UUID

from hydrolab.adapters.local.run_executor import extract_archive
from hydrolab.core.errors import conflict, not_found, validation_error
from hydrolab.ports.dto import RunHandle, RunSpec, RunState, RunStatusSnapshot


class DockerGpuRunExecutor:
    """用 Docker SDK 启动 GPU 训练容器执行 Run。"""

    real_executor = True  # 显式能力标记：真实执行训练进程
    requires_image_digest = True

    def __init__(
        self,
        image_whitelist: list[str] | None = None,
        docker_client=None,
        allow_network: bool = False,
        container_python: str = "/usr/local/bin/python",
        default_timeout_seconds: int = 6 * 3600,
        workspace_root=None,
        gpu_mode: str = "device_requests",
    ) -> None:
        if gpu_mode not in ("device_requests", "nvidia_runtime", "none"):
            raise validation_error("未知 gpu_mode", {"gpu_mode": gpu_mode})
        self._whitelist = {self._digest(i) for i in (image_whitelist or [])}
        self._client = docker_client
        self._allow_network = allow_network
        self._python = container_python
        self._default_timeout = default_timeout_seconds
        self._gpu_mode = gpu_mode
        self._workspace_root = (
            Path(workspace_root).expanduser().resolve() if workspace_root else Path(".hydrolab-data/runs")
        )
        self._runs: dict[str, RunStatusSnapshot] = {}
        self._container_ids: dict[str, str] = {}

    @staticmethod
    def _digest(image: str) -> str:
        if "@sha256:" in image:
            return image
        return "sha256:" + hashlib.sha256(image.encode()).hexdigest()

    def _validate_image(self, spec: RunSpec) -> None:
        if not spec.image_digest:
            raise validation_error("RunSpec.image_digest 不能为空")
        if not self._whitelist:
            raise validation_error("Docker Runner 未配置镜像白名单")
        if self._digest(spec.image_digest) not in self._whitelist:
            raise validation_error("镜像不在白名单", {"image": spec.image_digest})

    @staticmethod
    def _resolved_argv(argv: list[str], python: str) -> list[str]:
        resolved = list(argv)
        if resolved[0] in ("python", "python3", "python3.11", "python3.12"):
            resolved[0] = python
        return resolved

    # ---------- 工作区协议（与 SubprocessRunExecutor 一致，供 RunControlService 物化代码/数据） ----------
    def workspace_for(self, run_id: UUID) -> Path:
        return self._workspace_root / str(run_id)

    def prepare_workspace(
        self,
        run_id: UUID,
        archive: bytes | None,
        dataset_files: dict[str, bytes] | None = None,
    ) -> Path:
        """建立 <workspace>/<run_id>/{code,output} 并物化代码与数据（容器以只读挂载）。"""
        workspace = self.workspace_for(run_id)
        code_dir = workspace / "code"
        output_dir = workspace / "output"
        code_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        if os.geteuid() == 0:
            os.chown(output_dir, 65534, 65534)
        if archive:
            extract_archive(archive, code_dir)
        if dataset_files:
            self._materialize_datasets(code_dir, dataset_files)
        return workspace

    def _get_client(self):
        if self._client is None:
            from docker import from_env

            self._client = from_env()
        return self._client

    async def recover(self, run_id: UUID) -> RunHandle:
        """Reattach to the deterministic container name after Worker restart."""
        import asyncio

        container = await asyncio.to_thread(self._get_client().containers.get, f"hydrolab-{run_id.hex}")
        external_id = f"docker-{run_id.hex[:12]}"
        self._container_ids[external_id] = container.id
        self._runs[external_id] = RunStatusSnapshot(run_id=run_id, state=RunState.RUNNING)
        return RunHandle(run_id=run_id, external_id=external_id, state=RunState.RUNNING)

    @staticmethod
    def _materialize_datasets(code_dir: Path, dataset_files: dict[str, bytes]) -> None:
        from hydrolab.adapters.local.run_executor import SubprocessRunExecutor

        SubprocessRunExecutor._materialize_datasets(code_dir, dataset_files)

    async def start(self, spec: RunSpec) -> RunHandle:
        import asyncio

        if not spec.argv:
            raise validation_error("RunSpec.argv 不能为空")
        self._validate_image(spec)
        external_id = f"docker-{spec.run_id.hex[:12]}"
        if external_id in self._runs:
            raise conflict("Run 已在执行", {"run_id": str(spec.run_id)})

        argv = self._resolved_argv(spec.argv, self._python)
        container_id = await asyncio.to_thread(self._create_container, spec, argv)
        self._container_ids[external_id] = container_id
        self._runs[external_id] = RunStatusSnapshot(run_id=spec.run_id, state=RunState.RUNNING)
        return RunHandle(run_id=spec.run_id, external_id=external_id, state=RunState.RUNNING)

    def _create_container(self, spec: RunSpec, argv: list[str]) -> str:
        if self._client is None:
            from docker import from_env

            client = from_env()
        else:
            client = self._client

        device_requests: list[dict] = []
        runtime: str | None = None
        if spec.gpu_count > 0 and self._gpu_mode == "device_requests":
            request = {
                "Driver": "nvidia",
                "Count": len(spec.gpu_indices) if spec.gpu_indices else spec.gpu_count,
                "Capabilities": [["gpu"]],
            }
            if spec.gpu_indices:
                request.pop("Count")
                request["DeviceIDs"] = [str(index) for index in spec.gpu_indices]
            device_requests.append(request)
        elif spec.gpu_count > 0 and self._gpu_mode == "nvidia_runtime":
            # CDI 模式宿主机：经 nvidia container runtime 注入；租约到的物理卡序号
            # 通过 NVIDIA_VISIBLE_DEVICES 暴露，容器内序号重排为 0..n-1。
            runtime = "nvidia"

        env = dict(spec.env)
        env["HYDROLAB_RUN_ID"] = str(spec.run_id)
        env["HYDROLAB_OUTPUT_DIR"] = "/workspace/output"
        if self._gpu_mode != "none":
            # Container CUDA ordinals are local to the set exposed by DeviceIDs/DeviceRequests.
            env["CUDA_VISIBLE_DEVICES"] = ",".join(str(i) for i in range(spec.gpu_count))
        if runtime == "nvidia":
            env["NVIDIA_VISIBLE_DEVICES"] = (
                ",".join(str(index) for index in spec.gpu_indices) if spec.gpu_indices else "all"
            )
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        volumes: dict[str, dict[str, str]] = {}
        for index, host_path in enumerate(spec.read_only_mounts):
            path = Path(host_path).expanduser().resolve()
            if not path.exists():
                raise validation_error("只读工作区不存在", {"path": str(path)})
            bind = "/workspace/code" if index == 0 else f"/workspace/readonly-{index}"
            volumes[str(path)] = {"bind": bind, "mode": "ro"}
        if spec.writable_mount:
            output_path = Path(spec.writable_mount).expanduser().resolve()
            if not output_path.is_dir():
                raise validation_error("可写工作区不存在", {"path": str(output_path)})
            volumes[str(output_path)] = {"bind": "/workspace/output", "mode": "rw"}

        run_kwargs: dict = dict(
            name=f"hydrolab-{spec.run_id.hex}",
            labels={"hydrolab.run_id": str(spec.run_id)},
            image=spec.image_digest,
            command=argv,  # 直传 argv，禁止 shell
            working_dir="/workspace/code",
            user="65534:65534",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            environment=env,
            detach=True,
            network_disabled=not self._allow_network,
            device_requests=device_requests,
            volumes=volumes,
        )
        if runtime is not None:
            run_kwargs["runtime"] = runtime
        container = client.containers.run(**run_kwargs)
        return container.id

    async def status(self, handle: RunHandle) -> RunStatusSnapshot:
        snapshot = self._runs.get(handle.external_id)
        if snapshot is None:
            raise not_found("执行实例不存在")
        # 容器终态由 Runner Controller / 采集器负责；此处返回最近快照
        return snapshot

    async def cancel(self, handle: RunHandle) -> None:
        import asyncio

        snapshot = self._runs.get(handle.external_id)
        if snapshot is None:
            raise not_found("执行实例不存在")
        if snapshot.state in (RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED):
            return
        container_id = self._container_ids.get(handle.external_id)
        if container_id:
            container = await asyncio.to_thread(self._get_client().containers.get, container_id)
            await asyncio.to_thread(container.remove, force=True)
            self._container_ids.pop(handle.external_id, None)
        snapshot.state = RunState.CANCELLED

    async def wait(
        self, external_id: str, timeout: float | None = None  # noqa: ASYNC109 - public wait contract
    ) -> RunStatusSnapshot:
        """等待容器退出并回收容器资源，供 RunControlService.await_completion 调用。"""
        import asyncio

        snapshot = self._runs.get(external_id)
        if snapshot is None:
            raise not_found("执行实例不存在")
        container_id = self._container_ids.get(external_id)
        if not container_id:
            return snapshot
        try:
            client = self._client
            if client is None:
                from docker import from_env

                client = from_env()
            container = await asyncio.to_thread(client.containers.get, container_id)
            if timeout == 0:
                await asyncio.to_thread(container.reload)
                state = container.attrs["State"]
                if state.get("Running"):
                    return snapshot
                snapshot.exit_code = int(state.get("ExitCode", 1))
                snapshot.state = RunState.SUCCEEDED if snapshot.exit_code == 0 else RunState.FAILED
                return snapshot
            result = await asyncio.wait_for(
                asyncio.to_thread(container.wait),
                timeout=timeout or self._default_timeout,
            )
            exit_code = int(result.get("StatusCode", 1) if isinstance(result, dict) else result)
            snapshot.exit_code = exit_code
            snapshot.state = RunState.SUCCEEDED if exit_code == 0 else RunState.FAILED
            snapshot.message = None if exit_code == 0 else f"容器退出码 {exit_code}"
            try:
                await asyncio.to_thread(container.remove, force=True)
            except Exception:
                pass
        except TimeoutError:
            try:
                await asyncio.to_thread(container.kill)
                await asyncio.to_thread(container.remove, force=True)
            except Exception:
                pass
            snapshot.state = RunState.FAILED
            snapshot.exit_code = -1
            snapshot.message = "容器执行超时"
        except Exception as exc:
            snapshot.state = RunState.FAILED
            snapshot.exit_code = -1
            snapshot.message = f"容器状态回收失败: {exc.__class__.__name__}"
        return snapshot

    async def cleanup(self, external_id: str) -> None:
        import asyncio

        container_id = self._container_ids.get(external_id)
        if container_id:
            container = await asyncio.to_thread(self._get_client().containers.get, container_id)
            await asyncio.to_thread(container.remove, force=True)
            self._container_ids.pop(external_id, None)

    async def list_labeled_containers(self) -> list[tuple[UUID, str]]:
        """列出所有带 hydrolab.run_id label 的容器，供对账器清理终态遗留容器。"""
        import asyncio

        import docker

        try:
            client = self._get_client()
        except Exception:
            return []
        try:
            containers = await asyncio.to_thread(
                client.containers.list, all=True, filters={"label": "hydrolab.run_id"}
            )
        except docker.errors.DockerException:
            return []
        result: list[tuple[UUID, str]] = []
        for container in containers:
            label = container.labels.get("hydrolab.run_id")
            if not label:
                continue
            try:
                run_id = UUID(str(label))
            except ValueError:
                continue
            external_id = f"docker-{run_id.hex[:12]}"
            self._container_ids[external_id] = container.id
            result.append((run_id, external_id))
        return result

    async def healthcheck(self) -> bool:
        import asyncio

        try:
            if self._client is None:
                from docker import from_env

                client = from_env()
            else:
                client = self._client
            await asyncio.to_thread(client.ping)
            return True
        except Exception:
            return False
