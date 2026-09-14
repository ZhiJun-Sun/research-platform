"""结果、指标、图表、导出、产物 ORM 模型（B8）。"""

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from hydrolab.db.base import Base, UTCDateTime, json_column, uuid_column


class ResultModel(Base):
    __tablename__ = "results"

    id = mapped_column(uuid_column(), primary_key=True)
    run_id = mapped_column(uuid_column(), ForeignKey("runs.id"), index=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    dataset_version_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at = mapped_column(UTCDateTime())


class MetricPointModel(Base):
    __tablename__ = "metric_points"

    id = mapped_column(uuid_column(), primary_key=True)
    result_id = mapped_column(uuid_column(), ForeignKey("results.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    value: Mapped[float] = mapped_column(Float)
    split: Mapped[str] = mapped_column(String(20), default="test")
    horizon: Mapped[int | None] = mapped_column(Integer, nullable=True)
    basin_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ResultArtifactModel(Base):
    __tablename__ = "result_artifacts"

    id = mapped_column(uuid_column(), primary_key=True)
    result_id = mapped_column(uuid_column(), ForeignKey("results.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    object_key: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(100))


class PlotSpecModel(Base):
    __tablename__ = "plot_specs"

    id = mapped_column(uuid_column(), primary_key=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    result_ids = mapped_column(json_column())
    plot_type: Mapped[str] = mapped_column(String(80))
    data_selection = mapped_column(json_column())
    options = mapped_column(json_column())
    script_ref: Mapped[str] = mapped_column(String(200), default="hydrolab.plot.v1")
    created_at = mapped_column(UTCDateTime())


class ExportManifestModel(Base):
    __tablename__ = "export_manifests"

    id = mapped_column(uuid_column(), primary_key=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    result_ids = mapped_column(json_column())
    artifact_ids = mapped_column(json_column())
    manifest = mapped_column(json_column())
    created_at = mapped_column(UTCDateTime())