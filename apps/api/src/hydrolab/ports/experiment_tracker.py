"""实验跟踪端口（plans/05 第 6 节）。

实现：FakeExperimentTracker / NoopExperimentTracker → MlflowTrackingAdapter。
规则：跟踪失败不得反向覆盖业务 Run 状态；同步可重放。
"""

from typing import Protocol

from hydrolab.ports.dto import (
    ArtifactReference,
    ExternalRunRef,
    MetricRecord,
    TrackingContext,
)


class ExperimentTracker(Protocol):
    async def start_run(self, context: TrackingContext) -> ExternalRunRef: ...

    async def log_parameters(self, run: ExternalRunRef, values: dict[str, object]) -> None: ...

    async def log_metrics(self, run: ExternalRunRef, points: list[MetricRecord]) -> None: ...

    async def log_artifact_reference(
        self, run: ExternalRunRef, artifact: ArtifactReference
    ) -> None: ...

    async def finish_run(self, run: ExternalRunRef, status: str) -> None: ...

    async def healthcheck(self) -> bool: ...
