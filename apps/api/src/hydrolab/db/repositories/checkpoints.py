"""B7 Checkpoint SQL 仓储。"""

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hydrolab.checkpoints.entities import Checkpoint
from hydrolab.db.models.checkpoints import CheckpointModel


def _to_checkpoint(m: CheckpointModel) -> Checkpoint:
    return Checkpoint(
        id=m.id,
        owner_id=m.owner_id,
        source_run_id=m.source_run_id,
        source_experiment_version_id=m.source_experiment_version_id,
        artifact_key=m.artifact_key,
        artifact_sha256=m.artifact_sha256,
        model_signature=m.model_signature,
        feature_names=m.feature_names or [],
        target_names=m.target_names or [],
        scaler_signature=m.scaler_signature,
        optimizer_included=m.optimizer_included,
        scheduler_included=m.scheduler_included,
        source_config=m.source_config or {},
        created_at=m.created_at,
    )


class SqlCheckpoints:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, item: Checkpoint) -> Checkpoint:
        async with self._sf() as session:
            session.add(
                CheckpointModel(
                    id=item.id,
                    owner_id=item.owner_id,
                    source_run_id=item.source_run_id,
                    source_experiment_version_id=item.source_experiment_version_id,
                    artifact_key=item.artifact_key,
                    artifact_sha256=item.artifact_sha256,
                    model_signature=item.model_signature,
                    feature_names=item.feature_names,
                    target_names=item.target_names,
                    scaler_signature=item.scaler_signature,
                    optimizer_included=item.optimizer_included,
                    scheduler_included=item.scheduler_included,
                    source_config=item.source_config,
                    created_at=item.created_at,
                )
            )
            await session.commit()
            return item

    async def get(self, checkpoint_id: UUID) -> Checkpoint | None:
        async with self._sf() as session:
            m = await session.get(CheckpointModel, checkpoint_id)
            return _to_checkpoint(m) if m else None

    async def list_by_owner(self, owner_id: UUID) -> list[Checkpoint]:
        async with self._sf() as session:
            res = await session.execute(
                select(CheckpointModel)
                .where(CheckpointModel.owner_id == owner_id)
                .order_by(desc(CheckpointModel.created_at))
            )
            return [_to_checkpoint(m) for m in res.scalars().all()]
