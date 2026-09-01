"""Run 产物采集器：把训练进程写出的文件转成 HydroLab 结果域对象。

采集契约（以 da0 类工程的既有输出约定为基准，可通过 output_contract 覆盖）：

    <output|code>/experiments/<experiment>/
    ├── checkpoints/*.pth                → Checkpoint 候选
    ├── configs/*.json                   → 可复现配置 artifact
    └── results/<region>-<suffix>/
        ├── <model>.json                 → MetricPoint（按 horizon / Avg）
        ├── predictions.csv              → 预测 artifact
        ├── expert_usage-*.json          → 诊断 artifact
        └── *.png                        → 绘图 artifact

设计要点：
- 采集器只读取产物文件，不执行任何被采集代码；
- 训练脚本常写出 Infinity/NaN（如除零导致的 MAPE），标准 json 可解析但不可再序列化，
  因此统一消毒为 None 并跳过非有限指标，避免污染下游对比与导出；
- 所有产物内容按 sha256 入对象存储，形成可追溯 artifact。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

_METRIC_NAMES = ("RMSE", "MAE", "MAPE", "masked_mape", "NSE", "KGE")
_MAX_ARTIFACT_BYTES = 200 * 1024 * 1024

_ARTIFACT_KINDS: tuple[tuple[str, str], ...] = (
    ("predictions.csv", "predictions"),
    ("expert_usage", "diagnostics"),
    (".png", "plot"),
    (".pth", "checkpoint"),
)


@dataclass
class CollectedMetric:
    name: str
    value: float
    split: str = "test"
    horizon: int | None = None


@dataclass
class CollectedArtifact:
    kind: str
    relative_path: str
    object_key: str
    sha256: str
    size_bytes: int


@dataclass
class CollectionReport:
    experiment_dirs: list[str] = field(default_factory=list)
    metrics: list[CollectedMetric] = field(default_factory=list)
    artifacts: list[CollectedArtifact] = field(default_factory=list)
    checkpoints: list[CollectedArtifact] = field(default_factory=list)
    configs: list[CollectedArtifact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.metrics and not self.artifacts and not self.checkpoints


def _sanitize(value: object) -> float | None:
    """把 Infinity/NaN/非数值统一转成 None。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def sanitize_json(payload: object) -> object:
    """递归消毒 JSON 结构，保证结果可被标准 JSON 再序列化。"""
    if isinstance(payload, dict):
        return {str(key): sanitize_json(item) for key, item in payload.items()}
    if isinstance(payload, list):
        return [sanitize_json(item) for item in payload]
    if isinstance(payload, bool) or payload is None or isinstance(payload, str):
        return payload
    if isinstance(payload, (int, float)):
        return _sanitize(payload)
    return str(payload)


def load_metrics_json(path: Path) -> tuple[list[CollectedMetric], list[str]]:
    """解析 <model>.json 指标文件。

    结构为 {"0": {...}, "1": {...}, "Avg": {...}, "Avg-Half": {...}}，
    数字键表示 horizon（0 → T+1）。
    """
    warnings: list[str] = []
    try:
        # 训练脚本用 json.dump 写出 Infinity，Python json 可读但非严格 JSON
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        return [], [f"{path.name}: 无法解析指标文件 ({exc})"]
    if not isinstance(raw, dict):
        return [], [f"{path.name}: 指标文件不是对象"]

    metrics: list[CollectedMetric] = []
    for group, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        horizon: int | None = None
        label = str(group)
        if re.fullmatch(r"\d+", label):
            horizon = int(label) + 1  # "0" → T+1
            suffix = f"T+{horizon}"
        else:
            suffix = label  # Avg / Avg-Half
        for name in _METRIC_NAMES:
            if name not in payload:
                continue
            value = _sanitize(payload[name])
            if value is None:
                warnings.append(f"{path.name}: {suffix}.{name} 非有限值，已跳过")
                continue
            metrics.append(
                CollectedMetric(name=f"{name}@{suffix}", value=value, horizon=horizon)
            )
    return metrics, warnings


def _classify(relative: str) -> str:
    name = Path(relative).name
    for token, kind in _ARTIFACT_KINDS:
        if token in name or name.endswith(token):
            return kind
    if relative.endswith(".json") and "/configs/" in relative:
        return "config"
    if relative.endswith(".json"):
        return "metrics"
    return "artifact"


def find_experiment_dirs(search_roots: list[Path]) -> list[Path]:
    """定位 experiments/<name> 目录。兼容脚本写到 output/ 或 code/ 下两种情况。"""
    found: list[Path] = []
    for root in search_roots:
        if not root.is_dir():
            continue
        base = root / "experiments"
        if base.is_dir():
            found.extend(sorted(child for child in base.iterdir() if child.is_dir()))
    return found


class ArtifactCollector:
    """从 Run 工作目录采集产物并写入对象存储。"""

    def __init__(self, storage: object, key_prefix: str = "run-artifacts") -> None:
        self._storage = storage
        self._prefix = key_prefix

    def collect(self, run_id: str, search_roots: list[Path]) -> CollectionReport:
        report = CollectionReport()
        experiment_dirs = find_experiment_dirs(search_roots)
        if not experiment_dirs:
            report.warnings.append("未发现 experiments/<name> 产物目录")
            return report

        for experiment_dir in experiment_dirs:
            report.experiment_dirs.append(experiment_dir.name)
            base = experiment_dir.parent.parent  # 用于计算相对路径
            for path in sorted(experiment_dir.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                try:
                    relative = path.relative_to(base).as_posix()
                except ValueError:
                    relative = path.name
                size = path.stat().st_size
                if size > _MAX_ARTIFACT_BYTES:
                    report.warnings.append(f"{relative}: 超过采集上限 {_MAX_ARTIFACT_BYTES} 字节，已跳过")
                    continue

                kind = _classify(relative)
                # 指标文件：既解析为 MetricPoint，也作为 artifact 留档
                if kind == "metrics" and "/results/" in relative:
                    metrics, warnings = load_metrics_json(path)
                    report.metrics.extend(metrics)
                    report.warnings.extend(warnings)

                data = path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                key = f"{self._prefix}/{run_id}/{digest[:12]}-{path.name}"
                put = getattr(self._storage, "put_bytes", None)
                if callable(put):
                    put(key, data)
                artifact = CollectedArtifact(
                    kind=kind, relative_path=relative, object_key=key, sha256=digest, size_bytes=size
                )
                if kind == "checkpoint":
                    report.checkpoints.append(artifact)
                elif kind == "config":
                    report.configs.append(artifact)
                else:
                    report.artifacts.append(artifact)

        if report.is_empty:
            report.warnings.append("产物目录存在但未采集到任何指标或文件")
        return report
