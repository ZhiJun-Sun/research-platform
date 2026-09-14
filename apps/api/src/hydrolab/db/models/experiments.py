"""实验、Draft、冻结版本、Run、RunStage、Outbox ORM 模型（B4）。"""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from hydrolab.db.base import Base, UTCDateTime, json_column, uuid_column


class DraftModel(Base):
    __tablename__ = "experiment_drafts"

    id = mapped_column(uuid_column(), primary_key=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    dataset_version_id = mapped_column(uuid_column(), nullable=True)
    code_version_id = mapped_column(uuid_column(), nullable=True)
    template_version_id = mapped_column(uuid_column(), nullable=True)
    environment_version_id = mapped_column(uuid_column(), nullable=True)
    parameter_values = mapped_column(json_column())
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at = mapped_column(UTCDateTime())
    updated_at = mapped_column(UTCDateTime())


class ExperimentModel(Base):
    __tablename__ = "experiments"

    id = mapped_column(uuid_column(), primary_key=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    created_at = mapped_column(UTCDateTime())
    updated_at = mapped_column(UTCDateTime())


class ExperimentVersionModel(Base):
    __tablename__ = "experiment_versions"
    __table_args__ = (
        # A4 并发分配：同一实验下 version_no 必须唯一（next_version_no 竞争时的兜底）。
        UniqueConstraint(
            "experiment_id", "version_no", name="uq_experiment_versions_experiment_id_version_no"
        ),
    )

    id = mapped_column(uuid_column(), primary_key=True)
    experiment_id = mapped_column(uuid_column(), ForeignKey("experiments.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    resolved_config = mapped_column(json_column())
    config_hash: Mapped[str] = mapped_column(String(100), index=True)
    frozen_at = mapped_column(UTCDateTime())
    created_at = mapped_column(UTCDateTime())


class RunModel(Base):
    __tablename__ = "runs"
    __table_args__ = (
        # B4 幂等提交：同一 owner 的同一幂等键只允许存在一个 Run。
        UniqueConstraint("owner_id", "idempotency_key", name="uq_runs_owner_idempotency_key"),
    )

    id = mapped_column(uuid_column(), primary_key=True)
    experiment_id = mapped_column(uuid_column(), ForeignKey("experiments.id"), index=True)
    experiment_version_id = mapped_column(uuid_column(), ForeignKey("experiment_versions.id"), index=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default="QUEUED")
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    created_at = mapped_column(UTCDateTime(), index=True)
    updated_at = mapped_column(UTCDateTime())


class RunStageModel(Base):
    __tablename__ = "run_stages"

    id = mapped_column(uuid_column(), primary_key=True)
    run_id = mapped_column(uuid_column(), ForeignKey("runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(20))
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    created_at = mapped_column(UTCDateTime())


class OutboxModel(Base):
    __tablename__ = "outbox_events"

    id = mapped_column(uuid_column(), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(40), index=True)
    aggregate_id = mapped_column(uuid_column(), index=True)
    topic: Mapped[str] = mapped_column(String(120))
    payload = mapped_column(json_column())
    status: Mapped[str] = mapped_column(String(20), index=True, default="PENDING")
    created_at = mapped_column(UTCDateTime(), index=True)
    published_at = mapped_column(UTCDateTime(), nullable=True)