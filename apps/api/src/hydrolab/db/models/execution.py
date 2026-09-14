"""执行控制与观测 ORM 模型（B5/B6：GPU 租约、执行、事件、日志、资源采样）。

事件/日志/资源采样使用数据库自增主键（int），与内存实现的单调 id 语义一致。
"""

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from hydrolab.db.base import Base, UTCDateTime, json_column, uuid_column


class GpuLeaseModel(Base):
    __tablename__ = "gpu_leases"

    id = mapped_column(uuid_column(), primary_key=True)
    gpu_index: Mapped[int] = mapped_column(Integer, unique=True)
    run_id = mapped_column(uuid_column(), ForeignKey("runs.id"), index=True)
    expires_at = mapped_column(UTCDateTime())
    heartbeat_at = mapped_column(UTCDateTime())
    created_at = mapped_column(UTCDateTime())


class RunExecutionModel(Base):
    __tablename__ = "run_executions"

    run_id = mapped_column(uuid_column(), ForeignKey("runs.id"), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(200))
    gpu_indices = mapped_column(json_column())
    started_at = mapped_column(UTCDateTime())
    timeout_seconds: Mapped[int] = mapped_column(Integer)


class RunEventModel(Base):
    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    run_id = mapped_column(uuid_column(), ForeignKey("runs.id"), index=True)
    occurred_at = mapped_column(UTCDateTime())
    payload = mapped_column(json_column())


class RunLogChunkModel(Base):
    __tablename__ = "run_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id = mapped_column(uuid_column(), ForeignKey("runs.id"), index=True)
    content: Mapped[str] = mapped_column(String(10000))
    stream: Mapped[str] = mapped_column(String(20), default="stdout")
    created_at = mapped_column(UTCDateTime())


class ResourceSampleModel(Base):
    __tablename__ = "resource_samples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id = mapped_column(uuid_column(), ForeignKey("runs.id"), index=True)
    gpu_index: Mapped[int] = mapped_column(Integer)
    utilization_percent: Mapped[float] = mapped_column(Float)
    memory_used_mb: Mapped[int] = mapped_column(Integer)
    memory_total_mb: Mapped[int] = mapped_column(Integer)
    sampled_at = mapped_column(UTCDateTime())