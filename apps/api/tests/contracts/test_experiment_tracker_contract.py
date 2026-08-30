"""ExperimentTracker 端口契约测试。"""

from uuid import uuid4

import pytest

from hydrolab.adapters.fake import FakeExperimentTracker, NoopExperimentTracker
from hydrolab.core.errors import AppError
from hydrolab.ports import ExperimentTracker
from hydrolab.ports.dto import ArtifactReference, MetricRecord, TrackingContext


@pytest.fixture(params=["fake", "noop"])
def tracker(request: pytest.FixtureRequest) -> ExperimentTracker:
    if request.param == "fake":
        return FakeExperimentTracker()
    return NoopExperimentTracker()


def _context() -> TrackingContext:
    return TrackingContext(
        run_id=uuid4(), experiment_version_id=uuid4(), display_name="contract-run"
    )


async def test_full_tracking_lifecycle(tracker: ExperimentTracker) -> None:
    ref = await tracker.start_run(_context())
    assert ref.external_run_id

    await tracker.log_parameters(ref, {"lr": 0.001, "epochs": 10})
    await tracker.log_metrics(
        ref, [MetricRecord(name="nse", value=0.82, step=10, split="val")]
    )
    await tracker.log_artifact_reference(
        ref,
        ArtifactReference(
            artifact_id=uuid4(), kind="checkpoint", uri="s3://hydrolab/ckpt/1", sha256="ab"
        ),
    )
    await tracker.finish_run(ref, "SUCCEEDED")
    assert await tracker.healthcheck() is True


async def test_noop_tracker_marks_system_none() -> None:
    tracker = NoopExperimentTracker()
    ref = await tracker.start_run(_context())
    assert ref.system == "none"


async def test_fake_tracker_failure_does_not_corrupt_records() -> None:
    tracker = FakeExperimentTracker()
    ref = await tracker.start_run(_context())
    tracker.injector.inject_failure(
        "log_metrics", AppError("DEPENDENCY_UNAVAILABLE", "mlflow down")
    )
    with pytest.raises(AppError):
        await tracker.log_metrics(ref, [MetricRecord(name="nse", value=0.5, step=1)])
    # 失败不产生半写入；重放后完整可见
    await tracker.log_metrics(ref, [MetricRecord(name="nse", value=0.5, step=1)])
    assert len(tracker.metrics[ref.external_run_id]) == 1
