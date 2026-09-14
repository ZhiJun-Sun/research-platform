"""SubprocessRunExecutor：在本机以子进程真实执行 Run。

定位（plans/05）：
- 这是 FakeRunExecutor 与 DockerGpuRunExecutor 之间的可用实现，用于无 Docker/GPU 的
  开发机与单机部署真实跑通训练链路；
- 生产禁止启用（settings.validate_production 会拒绝），因为它缺少容器级隔离。

安全与可复现约束：
- argv 直传，**从不经过 shell**，避免命令注入；
- 每个 Run 获得独立工作目录：<workspace>/<run_id>/{code,output}；
- 代码来自不可变 CodeVersion 的 ZIP，解包时校验路径穿越与符号链接；
- 只读数据以符号链接挂载进工作目录，训练进程不应写入数据目录；
- stdout/stderr 合并落盘并按行回调，供上层写入 RunEvent/日志；
- 超时与取消都作用于整个进程组，防止孤儿子进程。
"""

from __future__ import annotations

import asyncio
import os
import signal
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from uuid import UUID

from hydrolab.core.errors import not_found, validation_error
from hydrolab.ports.dto import RunHandle, RunSpec, RunState, RunStatusSnapshot

LogSink = Callable[[UUID, str], Awaitable[None]]


@dataclass
class _Process:
    run_id: UUID
    workspace: Path
    process: asyncio.subprocess.Process | None = None
    state: RunState = RunState.PREPARING
    exit_code: int | None = None
    message: str | None = None
    task: asyncio.Task[None] | None = None
    log_path: Path | None = None
    cancelled: bool = False
    tail: list[str] = field(default_factory=list)


def extract_archive(archive: bytes, target: Path) -> list[str]:
    """安全解包 ZIP 到 target。拒绝绝对路径、路径穿越与符号链接。"""

    target.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    root = target.resolve()
    import io

    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        for info in zf.infolist():
            name = info.filename
            if not name:
                continue
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts:
                raise validation_error("代码包含非法路径", {"path": name})
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise validation_error("代码包不允许符号链接", {"path": name})
            destination = (root / name).resolve()
            if root not in destination.parents and destination != root:
                raise validation_error("代码包路径逃逸", {"path": name})
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(zf.read(info))
            written.append(name)
    return written


class SubprocessRunExecutor:
    """真实子进程执行器。"""

    real_executor = True  # 显式能力标记：真实执行训练进程

    def __init__(
        self,
        workspace_root: Path,
        python_executable: str | None = None,
        data_root: Path | None = None,
        log_sink: LogSink | None = None,
        default_timeout_seconds: int = 6 * 3600,
    ) -> None:
        import sys

        self._workspace_root = Path(workspace_root).expanduser().resolve()
        self._python = python_executable or sys.executable
        self._data_root = Path(data_root).expanduser().resolve() if data_root else None
        self._log_sink = log_sink
        self._default_timeout = default_timeout_seconds
        self._runs: dict[str, _Process] = {}

    # ---------- 工作区准备 ----------
    def workspace_for(self, run_id: UUID) -> Path:
        return self._workspace_root / str(run_id)

    def prepare_workspace(
        self,
        run_id: UUID,
        archive: bytes | None,
        dataset_files: dict[str, bytes] | None = None,
    ) -> Path:
        """建立 <workspace>/<run_id>/{code,output} 并物化代码与数据。

        数据来源有两条互斥路径，前者优先：
        1. dataset_files —— 由冻结 DatasetVersion 取回的内容，逐文件写入
           code/datasets/，保留包内原始相对路径。这是可复现的正道：
           跑哪个数据版本完全由 Run 自身决定。
        2. self._data_root —— 全局只读目录软链接，仅作为未选定数据版本时的
           兼容兜底（早期联调遗留），不参与版本追溯。
        """

        workspace = self.workspace_for(run_id)
        code_dir = workspace / "code"
        output_dir = workspace / "output"
        code_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        if archive:
            extract_archive(archive, code_dir)
        if dataset_files:
            self._materialize_datasets(code_dir, dataset_files)
        elif self._data_root and self._data_root.is_dir():
            # 未选定数据版本时的兼容路径：以符号链接暴露为 code/datasets，
            # 让原有相对路径 "datasets/xxx" 仍然生效。
            link = code_dir / "datasets"
            if not link.exists():
                try:
                    link.symlink_to(self._data_root, target_is_directory=True)
                except OSError:
                    pass
        return workspace

    @staticmethod
    def _materialize_datasets(code_dir: Path, dataset_files: dict[str, bytes]) -> None:
        """把数据集内容写入 code/datasets/，逐条防御路径穿越。

        若代码包里已存在 datasets 软链接（兼容路径残留），必须先摘除，
        否则写入会穿透到全局只读目录，既污染共享数据又破坏可复现性。
        """
        target_root = code_dir / "datasets"
        if target_root.is_symlink():
            target_root.unlink()
        target_root.mkdir(parents=True, exist_ok=True)
        resolved_root = target_root.resolve()
        for relative_path, payload in dataset_files.items():
            candidate = (target_root / relative_path).resolve()
            if resolved_root != candidate and resolved_root not in candidate.parents:
                raise validation_error(
                    "数据集文件路径越界", {"path": relative_path}
                )
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(payload)

    # ---------- RunExecutor 端口 ----------
    async def start(self, spec: RunSpec) -> RunHandle:
        if not spec.argv:
            raise validation_error("RunSpec.argv 不能为空")
        external_id = f"subproc-{spec.run_id.hex[:12]}"
        existing = self._runs.get(external_id)
        if existing and existing.state in (RunState.RUNNING, RunState.PREPARING):
            from hydrolab.core.errors import conflict

            raise conflict("Run 已在执行", {"run_id": str(spec.run_id)})

        workspace = self.workspace_for(spec.run_id)
        code_dir = workspace / "code"
        if not code_dir.is_dir():
            raise validation_error("工作目录未准备，请先 prepare_workspace", {"run_id": str(spec.run_id)})

        argv = list(spec.argv)
        # 约定：argv[0] == "python" 时替换为受控解释器，避免依赖 PATH
        if argv[0] in ("python", "python3"):
            argv[0] = self._python

        env = os.environ.copy()
        env.update(spec.env)
        env.setdefault("PYTHONUNBUFFERED", "1")
        env["HYDROLAB_RUN_ID"] = str(spec.run_id)
        env["HYDROLAB_OUTPUT_DIR"] = str(workspace / "output")
        # 无 GPU 时显式置空，避免代码盲目使用 cuda
        if spec.gpu_count <= 0:
            env["CUDA_VISIBLE_DEVICES"] = ""

        record = _Process(run_id=spec.run_id, workspace=workspace, state=RunState.PREPARING)
        record.log_path = workspace / "run.log"
        self._runs[external_id] = record

        timeout = spec.timeout_seconds or self._default_timeout
        record.task = asyncio.create_task(self._run(external_id, record, argv, code_dir, env, timeout))
        return RunHandle(run_id=spec.run_id, external_id=external_id, state=RunState.RUNNING)

    async def _run(
        self,
        external_id: str,
        record: _Process,
        argv: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout: int,
    ) -> None:
        log_file = record.log_path
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,  # 独立进程组，便于整组取消
            )
        except FileNotFoundError as exc:
            record.state, record.exit_code = RunState.FAILED, 127
            record.message = f"无法启动进程: {exc}"
            await self._emit(record, f"[hydrolab] 启动失败: {exc}\n")
            return
        except Exception as exc:  # noqa: BLE001 - 需要把任何启动异常转成 Run 失败
            record.state, record.exit_code = RunState.FAILED, 1
            record.message = f"启动异常: {exc}"
            await self._emit(record, f"[hydrolab] 启动异常: {exc}\n")
            return

        record.process = process
        record.state = RunState.RUNNING
        await self._emit(record, f"[hydrolab] 执行: {' '.join(argv)}\n")

        handle = None
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            handle = log_file.open("a", encoding="utf-8", errors="replace")

        async def pump() -> None:
            assert process.stdout is not None
            while True:
                raw = await process.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace")
                if handle is not None:
                    handle.write(line)
                    handle.flush()
                await self._emit(record, line)

        try:
            await asyncio.wait_for(pump(), timeout=timeout)
            await asyncio.wait_for(process.wait(), timeout=60)
            record.exit_code = process.returncode
        except asyncio.TimeoutError:
            record.message = f"执行超过 {timeout} 秒，已终止"
            await self._emit(record, f"[hydrolab] {record.message}\n")
            self._kill_group(process)
            record.exit_code = process.returncode if process.returncode is not None else -1
        except asyncio.CancelledError:
            self._kill_group(process)
            record.state = RunState.CANCELLED
            raise
        finally:
            if handle is not None:
                handle.close()

        if record.cancelled:
            record.state = RunState.CANCELLED
        elif record.exit_code == 0:
            record.state = RunState.SUCCEEDED
        else:
            record.state = RunState.FAILED
            record.message = record.message or f"进程退出码 {record.exit_code}"
        await self._emit(record, f"[hydrolab] 结束 state={record.state.value} exit_code={record.exit_code}\n")

    @staticmethod
    def _kill_group(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.kill()
            except ProcessLookupError:
                pass

    async def _emit(self, record: _Process, line: str) -> None:
        record.tail.append(line)
        if len(record.tail) > 500:
            del record.tail[: len(record.tail) - 500]
        if self._log_sink is not None:
            try:
                await self._log_sink(record.run_id, line)
            except Exception:  # noqa: BLE001 - 日志下游失败不应影响训练
                pass

    async def status(self, handle: RunHandle) -> RunStatusSnapshot:
        record = self._runs.get(handle.external_id)
        if record is None:
            raise not_found("执行实例不存在")
        return RunStatusSnapshot(
            run_id=record.run_id, state=record.state, exit_code=record.exit_code, message=record.message
        )

    async def cancel(self, handle: RunHandle) -> None:
        record = self._runs.get(handle.external_id)
        if record is None:
            raise not_found("执行实例不存在")
        if record.state in (RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED):
            return
        record.cancelled = True
        if record.process is not None:
            self._kill_group(record.process)
        record.state = RunState.CANCELLING

    async def wait(self, external_id: str, timeout: float | None = None) -> RunStatusSnapshot:
        """测试与同步验收辅助：等待执行结束。"""
        record = self._runs.get(external_id)
        if record is None:
            raise not_found("执行实例不存在")
        if record.task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(record.task), timeout=timeout)
            except asyncio.TimeoutError:
                pass
        return RunStatusSnapshot(
            run_id=record.run_id, state=record.state, exit_code=record.exit_code, message=record.message
        )

    def log_tail(self, external_id: str, limit: int = 200) -> list[str]:
        record = self._runs.get(external_id)
        return [] if record is None else record.tail[-limit:]

    async def healthcheck(self) -> bool:
        self._workspace_root.mkdir(parents=True, exist_ok=True)
        return self._workspace_root.is_dir()
