"""服务端科研图渲染：使用无界面 Agg 后端生成可发表的矢量与位图产物。"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from hydrolab.core.errors import validation_error
from hydrolab.results.entities import MetricPoint

COLORS = [
    "#27364B", "#2E86AB", "#F18F01", "#7A5195", "#2A9D8F", "#D1495B",
    "#5B8E7D", "#BC6C25", "#8C564B", "#577590", "#6A4C93",
]


@dataclass(frozen=True)
class RenderedPlot:
    filename: str
    content_type: str
    payload: bytes


def _render_figure(figure: plt.Figure, stem: str) -> list[RenderedPlot]:
    rendered: list[RenderedPlot] = []
    for extension, content_type in (("png", "image/png"), ("pdf", "application/pdf"), ("svg", "image/svg+xml")):
        buffer = io.BytesIO()
        figure.savefig(buffer, format=extension, dpi=220, bbox_inches="tight")
        rendered.append(RenderedPlot(f"{stem}.{extension}", content_type, buffer.getvalue()))
    plt.close(figure)
    return rendered


def _labels(options: dict[str, Any]) -> dict[str, Any]:
    labels = options.get("labels", {})
    if not isinstance(labels, dict):
        raise validation_error("options.labels 必须是结果 ID 到显示名称的映射")
    return labels


def _style(axis: plt.Axes) -> None:
    axis.grid(axis="y", alpha=0.25, linewidth=0.8)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def _horizon_values(
    result_ids: list[UUID], metrics_by_result: dict[UUID, list[MetricPoint]], metric_name: str
) -> tuple[list[int], dict[UUID, dict[int, float]]]:
    series: dict[UUID, dict[int, float]] = {}
    for result_id in result_ids:
        series[result_id] = {
            point.horizon: point.value
            for point in metrics_by_result[result_id]
            if point.name == metric_name and point.horizon is not None and point.basin_id is None and point.event_id is None
        }
    horizons = sorted({horizon for values in series.values() for horizon in values})
    if not horizons:
        raise validation_error("所选结果没有可用的 horizon 指标", {"metric": metric_name})
    return horizons, series
def render_grouped_metrics(
    *, result_ids: list[UUID], metrics_by_result: dict[UUID, list[MetricPoint]], options: dict[str, Any]
) -> list[RenderedPlot]:
    """Render global metrics for multiple results as PNG, PDF, SVG and source CSV."""
    requested = options.get("metrics", ["NSE", "KGE", "RMSE", "MAE"])
    if not isinstance(requested, list) or not all(isinstance(item, str) for item in requested):
        raise validation_error("options.metrics 必须是指标名数组")
    names = [item for item in requested if item]
    if not names:
        raise validation_error("至少选择一个指标")

    labels = options.get("labels", {})
    if not isinstance(labels, dict):
        raise validation_error("options.labels 必须是结果 ID 到显示名称的映射")
    title = str(options.get("title", "实验指标对比"))
    ylabel = str(options.get("y_label", "指标值"))

    values: dict[UUID, dict[str, float]] = {}
    for result_id in result_ids:
        values[result_id] = {
            point.name: point.value
            for point in metrics_by_result[result_id]
            if point.basin_id is None and point.event_id is None
        }

    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.unicode_minus": False})
    figure, axis = plt.subplots(figsize=(max(7.2, len(names) * 1.65), 4.8))
    positions = np.arange(len(names))
    width = 0.76 / len(result_ids)
    for index, result_id in enumerate(result_ids):
        offset = (index - (len(result_ids) - 1) / 2) * width
        display_name = str(labels.get(str(result_id), f"Result {index + 1}"))
        series = [values[result_id].get(name, float("nan")) for name in names]
        axis.bar(positions + offset, series, width=width, label=display_name, color=COLORS[index % len(COLORS)])
    axis.set_title(title, fontweight="bold")
    axis.set_xlabel(str(options.get("x_label", "评估指标")))
    axis.set_ylabel(ylabel)
    axis.set_xticks(positions, names)
    axis.grid(axis="y", alpha=0.25, linewidth=0.8)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.legend(frameon=False, loc=str(options.get("legend_location", "best")))
    figure.tight_layout()

    rendered = _render_figure(figure, "metrics_comparison")

    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(["metric", *[str(labels.get(str(item), item)) for item in result_ids]])
    for name in names:
        writer.writerow([name, *[values[item].get(name, "") for item in result_ids]])
    rendered.append(RenderedPlot("metrics_comparison.csv", "text/csv", text.getvalue().encode()))
    return rendered


def render_horizon_lines(
    *, result_ids: list[UUID], metrics_by_result: dict[UUID, list[MetricPoint]], options: dict[str, Any]
) -> list[RenderedPlot]:
    metric = str(options.get("metric", "NSE"))
    horizons, series = _horizon_values(result_ids, metrics_by_result, metric)
    labels = _labels(options)
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.unicode_minus": False})
    figure, axis = plt.subplots(figsize=(8.2, 4.8))
    for index, result_id in enumerate(result_ids):
        values = [series[result_id].get(horizon, float("nan")) for horizon in horizons]
        axis.plot(
            horizons, values, marker="o", linewidth=2, markersize=4.5,
            color=COLORS[index % len(COLORS)], label=str(labels.get(str(result_id), f"Result {index + 1}")),
        )
    axis.set_title(str(options.get("title", f"{metric} 随预测步长变化")), fontweight="bold")
    axis.set_xlabel(str(options.get("x_label", "预测步长")))
    axis.set_ylabel(str(options.get("y_label", metric)))
    axis.set_xticks(horizons, [f"T+{item}" for item in horizons])
    _style(axis)
    axis.legend(frameon=False, loc=str(options.get("legend_location", "best")))
    figure.tight_layout()
    rendered = _render_figure(figure, f"horizon_{metric.lower()}")
    text = io.StringIO(); writer = csv.writer(text)
    writer.writerow(["horizon", *[str(labels.get(str(item), item)) for item in result_ids]])
    for horizon in horizons:
        writer.writerow([horizon, *[series[item].get(horizon, "") for item in result_ids]])
    rendered.append(RenderedPlot(f"horizon_{metric.lower()}.csv", "text/csv", text.getvalue().encode()))
    return rendered


def render_nse_kge_panels(
    *, result_ids: list[UUID], metrics_by_result: dict[UUID, list[MetricPoint]], options: dict[str, Any]
) -> list[RenderedPlot]:
    labels = _labels(options)
    nse_horizons, nse = _horizon_values(result_ids, metrics_by_result, "NSE")
    kge_horizons, kge = _horizon_values(result_ids, metrics_by_result, "KGE")
    horizons = sorted(set(nse_horizons) | set(kge_horizons))
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.unicode_minus": False})
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharex=True)
    for axis, metric_name, series in zip(axes, ("NSE", "KGE"), (nse, kge), strict=True):
        for index, result_id in enumerate(result_ids):
            axis.plot(
                horizons, [series[result_id].get(item, float("nan")) for item in horizons], marker="o",
                linewidth=2, markersize=4.2, color=COLORS[index % len(COLORS)],
                label=str(labels.get(str(result_id), f"Result {index + 1}")),
            )
        axis.set_title(metric_name, fontweight="bold")
        axis.set_xlabel(str(options.get("x_label", "预测步长")))
        axis.set_ylabel(metric_name)
        axis.set_xticks(horizons, [f"T+{item}" for item in horizons])
        _style(axis)
    axes[1].legend(frameon=False, loc=str(options.get("legend_location", "best")))
    figure.suptitle(str(options.get("title", "NSE / KGE 随预测步长变化")), fontweight="bold")
    figure.tight_layout()
    rendered = _render_figure(figure, "horizon_nse_kge")
    text = io.StringIO(); writer = csv.writer(text)
    writer.writerow(["horizon", *[f"{labels.get(str(item), item)} NSE" for item in result_ids], *[f"{labels.get(str(item), item)} KGE" for item in result_ids]])
    for horizon in horizons:
        writer.writerow([horizon, *[nse[item].get(horizon, "") for item in result_ids], *[kge[item].get(horizon, "") for item in result_ids]])
    rendered.append(RenderedPlot("horizon_nse_kge.csv", "text/csv", text.getvalue().encode()))
    return rendered


def render_basin_metric_distribution(
    *, result_ids: list[UUID], metrics_by_result: dict[UUID, list[MetricPoint]], options: dict[str, Any]
) -> list[RenderedPlot]:
    """Compare the distribution of one metric across basins for selected experiments."""
    metric = str(options.get("metric", "NSE"))
    labels = _labels(options)
    values: list[list[float]] = []
    display_names: list[str] = []
    for index, result_id in enumerate(result_ids):
        series = [
            point.value
            for point in metrics_by_result[result_id]
            if point.name == metric and point.basin_id is not None and point.event_id is None
        ]
        if not series:
            raise validation_error("所选结果没有逐流域指标", {"metric": metric, "result_id": str(result_id)})
        values.append(series)
        display_names.append(str(labels.get(str(result_id), f"Result {index + 1}")))
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.unicode_minus": False})
    figure, axis = plt.subplots(figsize=(max(7.2, len(result_ids) * 1.8), 4.8))
    boxes = axis.boxplot(values, tick_labels=display_names, patch_artist=True, showmeans=True)
    for index, patch in enumerate(boxes["boxes"]):
        patch.set_facecolor(COLORS[index % len(COLORS)])
        patch.set_alpha(0.75)
    axis.set_title(str(options.get("title", f"逐流域 {metric} 分布")), fontweight="bold")
    axis.set_xlabel(str(options.get("x_label", "实验")))
    axis.set_ylabel(str(options.get("y_label", metric)))
    _style(axis)
    figure.tight_layout()
    rendered = _render_figure(figure, f"basin_{metric.lower()}_distribution")
    text = io.StringIO(); writer = csv.writer(text)
    writer.writerow(["result", "basin_id", metric])
    for index, result_id in enumerate(result_ids):
        for point in metrics_by_result[result_id]:
            if point.name == metric and point.basin_id is not None and point.event_id is None:
                writer.writerow([display_names[index], point.basin_id, point.value])
    rendered.append(RenderedPlot(f"basin_{metric.lower()}_distribution.csv", "text/csv", text.getvalue().encode()))
    return rendered


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
