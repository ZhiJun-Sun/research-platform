"""目录快照导入、安全解包、子进程执行与产物采集测试。

这些测试覆盖真实执行链路的关键契约，不依赖 da0 也可运行；
da0 真实端到端验收见 scripts/verify-da0-e2e.sh。
"""

import asyncio
import json
import sys
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest

from hydrolab.adapters.local.run_executor import SubprocessRunExecutor, extract_archive
from hydrolab.code_assets.directory_import import DirectoryImportService, snapshot_directory
from hydrolab.core.errors import AppError
from hydrolab.execution.collector import ArtifactCollector, load_metrics_json, sanitize_json
from hydrolab.ports.dto import RunSpec


class _Storage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, key: str, data: bytes) -> None:
        self.objects[key] = data


def _project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (root / "requirements.txt").write_text("torch\n", encoding="utf-8")
    pkg = root / "utils"
    pkg.mkdir(exist_ok=True)
    (pkg / "tools.py").write_text("VALUE = 1\n", encoding="utf-8")
    # 应被默认忽略的内容
    venv = root / ".venv" / "bin"
    venv.mkdir(parents=True, exist_ok=True)
    (venv / "python").write_text("binary", encoding="utf-8")
    cache = root / "__pycache__"
    cache.mkdir(exist_ok=True)
    (cache / "main.cpython-39.pyc").write_text("cache", encoding="utf-8")
    data = root / "datasets"
    data.mkdir(exist_ok=True)
    (data / "big.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    return root


def test_snapshot_excludes_venv_cache_and_data(tmp_path: Path) -> None:
    snapshot = snapshot_directory(_project(tmp_path / "proj"))
    assert "main.py" in snapshot.files
    assert "utils/tools.py" in snapshot.files
    # 虚拟环境、缓存与数据目录必须被排除，避免把几十 GB 混进代码包
    assert not any(item.startswith(".venv") for item in snapshot.files)
    assert not any("__pycache__" in item for item in snapshot.files)
    assert not any(item.startswith("datasets") for item in snapshot.files)
    assert snapshot.detected_manifests == ["requirements.txt"]
    assert "main.py" in snapshot.entrypoints


def test_snapshot_is_deterministic_and_content_addressed(tmp_path: Path) -> None:
    first = snapshot_directory(_project(tmp_path / "a"))
    second = snapshot_directory(_project(tmp_path / "b"))
    # 相同内容 → 相同 content_hash，保证可复现与去重
    assert first.content_hash == second.content_hash
    (tmp_path / "b" / "main.py").write_text("print('changed')\n", encoding="utf-8")
    assert snapshot_directory(tmp_path / "b").content_hash != first.content_hash


def test_snapshot_honours_hydrolabignore(tmp_path: Path) -> None:
    root = _project(tmp_path / "proj")
    (root / "secret.py").write_text("TOKEN='x'\n", encoding="utf-8")
    (root / ".hydrolabignore").write_text("# comment\nsecret.py\n", encoding="utf-8")
    files = snapshot_directory(root).files
    assert "secret.py" not in files
    assert "main.py" in files


async def test_directory_import_rejects_paths_outside_allowlist(tmp_path: Path) -> None:
    allowed = _project(tmp_path / "allowed")
    outside = _project(tmp_path / "outside")
    service = DirectoryImportService(versions=None, storage=_Storage(), policy=None, allowed_roots=[allowed])
    with pytest.raises(AppError):
        service.preview(str(outside))
    with pytest.raises(AppError):
        service.preview("relative/path")
    resolved, snapshot = service.preview(str(allowed))
    assert resolved == allowed.resolve()
    assert snapshot.files


def test_extract_archive_rejects_path_traversal(tmp_path: Path) -> None:
    buffer = tmp_path / "evil.zip"
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("../escape.py", "x = 1")
    with pytest.raises(AppError):
        extract_archive(buffer.read_bytes(), tmp_path / "out")


def test_extract_archive_round_trips_snapshot(tmp_path: Path) -> None:
    snapshot = snapshot_directory(_project(tmp_path / "proj"))
    written = extract_archive(snapshot.archive, tmp_path / "code")
    assert "main.py" in written
    assert (tmp_path / "code" / "utils" / "tools.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_metrics_loader_maps_horizons_and_drops_infinite(tmp_path: Path) -> None:
    payload = {
        "0": {"RMSE": 2.2, "MAPE": float("inf"), "NSE": 0.99},
        "11": {"RMSE": 17.3, "NSE": 0.48},
        "Avg": {"RMSE": 9.76, "KGE": 0.86},
    }
    path = tmp_path / "kg_moe_ms.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    metrics, warnings = load_metrics_json(path)
    names = {item.name: item.value for item in metrics}
    # 数字键 "0" 表示 T+1
    assert names["RMSE@T+1"] == pytest.approx(2.2)
    assert names["RMSE@T+12"] == pytest.approx(17.3)
    assert names["KGE@Avg"] == pytest.approx(0.86)
    # Infinity 不能进入指标体系，否则污染对比与导出
    assert "MAPE@T+1" not in names
    assert any("非有限值" in item for item in warnings)


def test_sanitize_json_replaces_non_finite() -> None:
    cleaned = sanitize_json({"a": float("inf"), "b": [float("nan"), 1.5], "c": "ok"})
    assert cleaned == {"a": None, "b": [None, 1.5], "c": "ok"}
    # 消毒后必须可被标准 JSON 序列化
    assert json.loads(json.dumps(cleaned))["b"][1] == 1.5


def test_collector_reads_da0_style_outputs(tmp_path: Path) -> None:
    result_dir = tmp_path / "output" / "experiments" / "run1" / "results" / "bj-0200"
    result_dir.mkdir(parents=True)
    (result_dir / "kg_moe_ms.json").write_text(
        json.dumps({"Avg": {"RMSE": 9.7, "NSE": 0.79, "MAPE": float("inf")}}), encoding="utf-8"
    )
    (result_dir / "predictions.csv").write_text("t,y\n1,2\n", encoding="utf-8")
    (result_dir / "prediction_comparison.png").write_bytes(b"\x89PNG fake")
    (result_dir / "expert_usage-0200.json").write_text("{}", encoding="utf-8")
    ckpt_dir = tmp_path / "output" / "experiments" / "run1" / "checkpoints"
    ckpt_dir.mkdir(parents=True)
    (ckpt_dir / "kg_moe_ms-0200.pth").write_bytes(b"weights")
    cfg_dir = tmp_path / "output" / "experiments" / "run1" / "configs"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "kg_moe_ms-0200.json").write_text("{}", encoding="utf-8")

    storage = _Storage()
    report = ArtifactCollector(storage).collect("run-1", [tmp_path / "output"])

    assert report.experiment_dirs == ["run1"]
    assert {item.name for item in report.metrics} == {"RMSE@Avg", "NSE@Avg"}
    kinds = {item.kind for item in report.artifacts}
    assert {"predictions", "plot", "diagnostics"} <= kinds
    assert len(report.checkpoints) == 1
    assert len(report.configs) == 1
    # 所有产物内容都进入对象存储，形成可追溯 artifact
    assert len(storage.objects) == len(report.artifacts) + len(report.checkpoints) + len(report.configs)


async def test_subprocess_executor_runs_real_process_and_collects(tmp_path: Path) -> None:
    """真实子进程执行：写出 da0 风格产物，采集器应能读回指标。"""
    source = tmp_path / "proj"
    source.mkdir()
    (source / "main.py").write_text(
        "\n".join(
            [
                "import argparse, json, os",
                "from pathlib import Path",
                "p = argparse.ArgumentParser()",
                "p.add_argument('--experiment', default='x')",
                "p.add_argument('--epochs', type=int, default=1)",
                "p.add_argument('--output-dir')",
                "a = p.parse_args()",
                "print('training epochs', a.epochs, flush=True)",
                "root = Path(a.output_dir or os.environ['HYDROLAB_OUTPUT_DIR'])",
                "d = root/'experiments'/a.experiment/'results'/'bj-0200'",
                "d.mkdir(parents=True, exist_ok=True)",
                "(d/'kg_moe_ms.json').write_text(json.dumps({'Avg': {'RMSE': 1.5, 'NSE': 0.9}}))",
                "(d/'predictions.csv').write_text('t,y\\n1,2\\n')",
                "c = root/'experiments'/a.experiment/'checkpoints'",
                "c.mkdir(parents=True, exist_ok=True)",
                "(c/'m.pth').write_bytes(b'w')",
                "print('done', flush=True)",
            ]
        ),
        encoding="utf-8",
    )
    snapshot = snapshot_directory(source)

    lines: list[str] = []

    async def sink(run_id: object, line: str) -> None:
        lines.append(line)

    executor = SubprocessRunExecutor(
        workspace_root=tmp_path / "ws", python_executable=sys.executable, log_sink=sink
    )
    run_id = uuid4()
    workspace = executor.prepare_workspace(run_id, snapshot.archive)
    handle = await executor.start(
        RunSpec(
            run_id=run_id,
            argv=[
                "python",
                "main.py",
                "--experiment",
                "smoke",
                "--epochs",
                "1",
                "--output-dir",
                str(workspace / "output"),
            ],
            image_digest="local:subprocess",
            gpu_count=0,
        )
    )
    snapshot_status = await executor.wait(handle.external_id, timeout=120)
    assert snapshot_status.exit_code == 0, "".join(lines)
    assert snapshot_status.state.value == "SUCCEEDED"
    # stdout 必须被回流，供前端增量展示
    assert any("training epochs 1" in line for line in lines)

    report = ArtifactCollector(_Storage()).collect(str(run_id), [workspace / "output", workspace / "code"])
    assert {item.name for item in report.metrics} == {"RMSE@Avg", "NSE@Avg"}
    assert len(report.checkpoints) == 1


async def test_subprocess_executor_marks_failure_exit_code(tmp_path: Path) -> None:
    source = tmp_path / "proj"
    source.mkdir()
    (source / "main.py").write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    executor = SubprocessRunExecutor(workspace_root=tmp_path / "ws", python_executable=sys.executable)
    run_id = uuid4()
    executor.prepare_workspace(run_id, snapshot_directory(source).archive)
    handle = await executor.start(
        RunSpec(run_id=run_id, argv=["python", "main.py"], image_digest="local:subprocess")
    )
    status = await executor.wait(handle.external_id, timeout=60)
    assert status.state.value == "FAILED"
    assert status.exit_code == 3


async def test_subprocess_executor_cancel_terminates_process(tmp_path: Path) -> None:
    source = tmp_path / "proj"
    source.mkdir()
    (source / "main.py").write_text("import time\ntime.sleep(120)\n", encoding="utf-8")
    executor = SubprocessRunExecutor(workspace_root=tmp_path / "ws", python_executable=sys.executable)
    run_id = uuid4()
    executor.prepare_workspace(run_id, snapshot_directory(source).archive)
    handle = await executor.start(
        RunSpec(run_id=run_id, argv=["python", "main.py"], image_digest="local:subprocess")
    )
    await asyncio.sleep(1.0)
    await executor.cancel(handle)
    status = await executor.wait(handle.external_id, timeout=60)
    assert status.state.value == "CANCELLED"


async def test_prepare_workspace_materializes_selected_dataset(tmp_path: Path) -> None:
    """选定的数据集内容必须真正落到 code/datasets/ 并被训练代码读到。

    这是"选好数据集就能跑"的核心契约：以前 prepare_workspace 只物化代码，
    数据靠全局软链接，导致选哪个数据版本都跑同一份数据。
    """
    source = tmp_path / "proj"
    source.mkdir()
    # 训练代码按 da0 的习惯用相对路径读取 datasets/
    (source / "main.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "target = Path('datasets/81000200.csv').read_text()",
                "static = Path('datasets/camels/static.csv').read_text()",
                "print('basin=' + target.strip(), flush=True)",
                "print('static=' + static.strip(), flush=True)",
            ]
        ),
        encoding="utf-8",
    )

    lines: list[str] = []

    async def sink(run_id: object, line: str) -> None:
        lines.append(line)

    executor = SubprocessRunExecutor(
        workspace_root=tmp_path / "ws", python_executable=sys.executable, log_sink=sink
    )
    run_id = uuid4()
    executor.prepare_workspace(
        run_id,
        snapshot_directory(source).archive,
        {
            "81000200.csv": b"flow-of-basin-81000200",
            "camels/static.csv": b"static-attributes",
        },
    )

    workspace = executor.workspace_for(run_id)
    # 子目录结构必须保留，而不是被拍平
    assert (workspace / "code" / "datasets" / "81000200.csv").is_file()
    assert (workspace / "code" / "datasets" / "camels" / "static.csv").is_file()

    handle = await executor.start(
        RunSpec(run_id=run_id, argv=["python", "main.py"], image_digest="local:subprocess")
    )
    status = await executor.wait(handle.external_id, timeout=120)
    assert status.exit_code == 0, "".join(lines)
    assert any("basin=flow-of-basin-81000200" in line for line in lines)
    assert any("static=static-attributes" in line for line in lines)


async def test_dataset_materialization_replaces_global_symlink(tmp_path: Path) -> None:
    """选定数据版本时，必须摘掉全局 DATA_ROOT 软链接。

    否则写入会穿透到共享只读目录：既污染别人的数据，又让"跑的是哪份数据"
    无法追溯。
    """
    global_data = tmp_path / "global_data"
    global_data.mkdir()
    (global_data / "shared.csv").write_text("shared-and-must-not-be-touched", encoding="utf-8")

    source = tmp_path / "proj"
    source.mkdir()
    (source / "main.py").write_text("print('ok')\n", encoding="utf-8")

    executor = SubprocessRunExecutor(
        workspace_root=tmp_path / "ws",
        python_executable=sys.executable,
        data_root=global_data,
    )
    run_id = uuid4()
    executor.prepare_workspace(
        run_id, snapshot_directory(source).archive, {"only.csv": b"picked-version"}
    )

    datasets_dir = executor.workspace_for(run_id) / "code" / "datasets"
    assert not datasets_dir.is_symlink(), "选定数据版本后不应残留全局软链接"
    assert (datasets_dir / "only.csv").read_bytes() == b"picked-version"
    # 全局共享数据不应出现在本次 Run 的视野里，也不应被改动
    assert not (datasets_dir / "shared.csv").exists()
    assert (global_data / "shared.csv").read_text() == "shared-and-must-not-be-touched"


async def test_dataset_materialization_rejects_path_traversal(tmp_path: Path) -> None:
    """数据集文件名不得穿越出 datasets 目录。"""
    source = tmp_path / "proj"
    source.mkdir()
    (source / "main.py").write_text("print('ok')\n", encoding="utf-8")
    executor = SubprocessRunExecutor(
        workspace_root=tmp_path / "ws", python_executable=sys.executable
    )
    with pytest.raises(AppError):
        executor.prepare_workspace(
            uuid4(),
            snapshot_directory(source).archive,
            {"../../escaped.csv": b"evil"},
        )


async def test_fallback_to_global_data_root_when_no_dataset_selected(tmp_path: Path) -> None:
    """未选定数据版本时保留原有软链接兼容行为，不破坏既有联调流程。"""
    global_data = tmp_path / "global_data"
    global_data.mkdir()
    (global_data / "legacy.csv").write_text("legacy", encoding="utf-8")
    source = tmp_path / "proj"
    source.mkdir()
    (source / "main.py").write_text("print('ok')\n", encoding="utf-8")
    executor = SubprocessRunExecutor(
        workspace_root=tmp_path / "ws",
        python_executable=sys.executable,
        data_root=global_data,
    )
    run_id = uuid4()
    executor.prepare_workspace(run_id, snapshot_directory(source).archive, None)
    datasets_dir = executor.workspace_for(run_id) / "code" / "datasets"
    assert (datasets_dir / "legacy.csv").read_text() == "legacy"
