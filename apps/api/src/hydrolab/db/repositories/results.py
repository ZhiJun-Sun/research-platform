"""B8 结果、指标、图表、导出 SQL 仓储。"""

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hydrolab.db.models.results import (
    ExportManifestModel,
    MetricPointModel,
    PlotSpecModel,
    ResultArtifactModel,
    ResultModel,
)
from hydrolab.results.entities import ExportManifest, MetricPoint, PlotSpec, Result, ResultArtifact


def _to_result(m: ResultModel) -> Result:
    return Result(
        id=m.id,
        run_id=m.run_id,
        owner_id=m.owner_id,
        dataset_version_id=m.dataset_version_id,
        created_at=m.created_at,
    )


def _to_metric(m: MetricPointModel) -> MetricPoint:
    return MetricPoint(
        id=m.id,
        result_id=m.result_id,
        name=m.name,
        value=m.value,
        split=m.split,
        horizon=m.horizon,
        basin_id=m.basin_id,
        event_id=m.event_id,
    )


def _to_artifact(m: ResultArtifactModel) -> ResultArtifact:
    return ResultArtifact(
        id=m.id,
        result_id=m.result_id,
        kind=m.kind,
        object_key=m.object_key,
        sha256=m.sha256,
    )


def _to_plot(m: PlotSpecModel) -> PlotSpec:
    return PlotSpec(
        id=m.id,
        owner_id=m.owner_id,
        result_ids=[UUID(x) for x in (m.result_ids or [])],
        plot_type=m.plot_type,
        data_selection=m.data_selection or {},
        options=m.options or {},
        script_ref=m.script_ref,
        created_at=m.created_at,
    )


def _to_export(m: ExportManifestModel) -> ExportManifest:
    return ExportManifest(
        id=m.id,
        owner_id=m.owner_id,
        result_ids=[UUID(x) for x in (m.result_ids or [])],
        artifact_ids=[UUID(x) for x in (m.artifact_ids or [])],
        manifest=m.manifest or {},
        created_at=m.created_at,
    )


class SqlResults:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, item: Result) -> Result:
        async with self._sf() as session:
            session.add(
                ResultModel(
                    id=item.id,
                    run_id=item.run_id,
                    owner_id=item.owner_id,
                    dataset_version_id=item.dataset_version_id,
                    created_at=item.created_at,
                )
            )
            await session.commit()
            return item

    async def get(self, item_id: UUID) -> Result | None:
        async with self._sf() as session:
            m = await session.get(ResultModel, item_id)
            return _to_result(m) if m else None

    async def list_by_owner(self, owner_id: UUID) -> list[Result]:
        async with self._sf() as session:
            res = await session.execute(
                select(ResultModel)
                .where(ResultModel.owner_id == owner_id)
                .order_by(desc(ResultModel.created_at))
            )
            return [_to_result(m) for m in res.scalars().all()]

    async def list_by_run(self, run_id: UUID) -> list[Result]:
        async with self._sf() as session:
            res = await session.execute(
                select(ResultModel).where(ResultModel.run_id == run_id).order_by(desc(ResultModel.created_at))
            )
            return [_to_result(m) for m in res.scalars().all()]


class SqlMetrics:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add_many(self, items: list[MetricPoint]) -> list[MetricPoint]:
        async with self._sf() as session:
            session.add_all(
                [
                    MetricPointModel(
                        id=x.id,
                        result_id=x.result_id,
                        name=x.name,
                        value=x.value,
                        split=x.split,
                        horizon=x.horizon,
                        basin_id=x.basin_id,
                        event_id=x.event_id,
                    )
                    for x in items
                ]
            )
            await session.commit()
            return items

    async def list_by_result(self, result_id: UUID) -> list[MetricPoint]:
        async with self._sf() as session:
            res = await session.execute(
                select(MetricPointModel)
                .where(MetricPointModel.result_id == result_id)
                .order_by(MetricPointModel.id)
            )
            return [_to_metric(m) for m in res.scalars().all()]


class SqlArtifacts:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, item: ResultArtifact) -> ResultArtifact:
        async with self._sf() as session:
            session.add(
                ResultArtifactModel(
                    id=item.id,
                    result_id=item.result_id,
                    kind=item.kind,
                    object_key=item.object_key,
                    sha256=item.sha256,
                )
            )
            await session.commit()
            return item

    async def get(self, item_id: UUID) -> ResultArtifact | None:
        async with self._sf() as session:
            m = await session.get(ResultArtifactModel, item_id)
            return _to_artifact(m) if m else None

    async def list_by_result(self, result_id: UUID) -> list[ResultArtifact]:
        async with self._sf() as session:
            res = await session.execute(
                select(ResultArtifactModel).where(ResultArtifactModel.result_id == result_id)
            )
            return [_to_artifact(m) for m in res.scalars().all()]


class SqlPlots:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, item: PlotSpec) -> PlotSpec:
        async with self._sf() as session:
            session.add(
                PlotSpecModel(
                    id=item.id,
                    owner_id=item.owner_id,
                    result_ids=[str(x) for x in item.result_ids],
                    plot_type=item.plot_type,
                    data_selection=item.data_selection,
                    options=item.options,
                    script_ref=item.script_ref,
                    created_at=item.created_at,
                )
            )
            await session.commit()
            return item


class SqlExports:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, item: ExportManifest) -> ExportManifest:
        async with self._sf() as session:
            session.add(
                ExportManifestModel(
                    id=item.id,
                    owner_id=item.owner_id,
                    result_ids=[str(x) for x in item.result_ids],
                    artifact_ids=[str(x) for x in item.artifact_ids],
                    manifest=item.manifest,
                    created_at=item.created_at,
                )
            )
            await session.commit()
            return item
