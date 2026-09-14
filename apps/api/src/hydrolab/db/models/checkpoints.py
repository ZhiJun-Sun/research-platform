"""检查点 ORM 模型（B7）。"""

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from hydrolab.db.base import Base, UTCDateTime, json_column, uuid_column


class CheckpointModel(Base):
    __tablename__ = "checkpoints"

    id = mapped_column(uuid_column(), primary_key=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    source_run_id = mapped_column(uuid_column(), ForeignKey("runs.id"), index=True)
    source_experiment_version_id = mapped_column(uuid_column(), ForeignKey("experiment_versions.id"), index=True)
    artifact_key: Mapped[str] = mapped_column(String(500))
    artifact_sha256: Mapped[str] = mapped_column(String(100))
    model_signature: Mapped[str] = mapped_column(String(200))
    feature_names = mapped_column(json_column())
    target_names = mapped_column(json_column())
    scaler_signature: Mapped[str | None] = mapped_column(String(200), nullable=True)
    optimizer_included: Mapped[bool] = mapped_column(Boolean, default=False)
    scheduler_included: Mapped[bool] = mapped_column(Boolean, default=False)
    source_config = mapped_column(json_column())
    created_at = mapped_column(UTCDateTime())