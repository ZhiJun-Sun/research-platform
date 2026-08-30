"""Fake / Noop ExperimentTracker。

Fake：内存记录，支持故障注入与重放验证；
Noop：跟踪禁用时的显式空实现，system 标记为 "none"。
"""

from uuid import uuid4

from hydrolab.adapters.fake.base import FailureInjector
from hydrolab.ports.dto import (
    ArtifactReference,
    ExternalRunRef,
    MetricRecord,
    TrackingContext,
)


class FakeExperimentTracker:
    def __init__(self) -> None:
        self.injector = FailureInjector()
        self.runs: dict[str, TrackingContext] = {}
        self.params: dict[str, dict[str, object]] = {}
        self.metrics: dict[str, list[MetricRecord]] = {}
        self.artifacts: dict[str, list[ArtifactReference]] = {}
        self.finished: dict[str, str] = {}

    async def start_run(self, context: TrackingContext) -> ExternalRunRef:
        self.injector._record("start_run", context)
        ref = ExternalRunRef(system="fake", external_run_id=f"fake-run-{uuid4().hex[:12]}")
        self.runs[ref.external_run_id] = context
        return ref

    async def log_parameters(self, run: ExternalRunRef, values: dict[str, object]) -> None:
        self.injector._record("log_parameters", run, values)
        self.params.setdefault(run.external_run_id, {}).update(values)

    async def log_metrics(self, run: ExternalRunRef, points: list[MetricRecord]) -> None:
        self.injector._record("log_metrics", run, points)
        self.metrics.setdefault(run.external_run_id, []).extend(points)

    async def log_artifact_reference(
        self, run: ExternalRunRef, artifact: ArtifactReference
    ) -> None:
        self.injector._record("log_artifact_reference", run, artifact)
        self.artifacts.setdefault(run.external_run_id, []).append(artifact)

    async def finish_run(self, run: ExternalRunRef, status: str) -> None:
        self.injector._record("finish_run", run, status)
        self.finished[run.external_run_id] = status

    async def healthcheck(self) -> bool:
        self.injector._record("healthcheck")
        return True


class NoopExperimentTracker:
    """Tracker 禁用开关：不抛错、不记录，返回 system=none 引用。"""

    async def start_run(self, context: TrackingContext) -> ExternalRunRef:
        return ExternalRunRef(system="none", external_run_id=f"none-{context.run_id.hex}")

    async def log_parameters(self, run: ExternalRunRef, values: dict[str, object]) -> None:
        return None

    async def log_metrics(self, run: ExternalRunRef, points: list[MetricRecord]) -> None:
        return None

    async def log_artifact_reference(
        self, run: ExternalRunRef, artifact: ArtifactReference
    ) -> None:
        return None

    async def finish_run(self, run: ExternalRunRef, status: str) -> None:
        return None

    async def healthcheck(self) -> bool:
        return True
