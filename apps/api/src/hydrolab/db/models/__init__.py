"""ORM 表模型包。子模块按领域拆分，__init__ 统一导入以便 Alembic 发现全部 metadata。"""

from hydrolab.db.models.checkpoints import CheckpointModel
from hydrolab.db.models.code_assets import (
    CodeRepositoryModel,
    CodeVersionModel,
    EnvironmentModel,
    EnvironmentVersionModel,
    ParameterPresetModel,
    TemplateModel,
    TemplateVersionModel,
)
from hydrolab.db.models.datasets import (
    ArtifactModel,
    DatasetImportJobModel,
    DatasetModel,
    DatasetVersionModel,
    FieldMappingModel,
    FolderModel,
)
from hydrolab.db.models.execution import (
    GpuLeaseModel,
    ResourceSampleModel,
    RunEventModel,
    RunExecutionModel,
    RunLogChunkModel,
)
from hydrolab.db.models.experiments import (
    DraftModel,
    ExperimentModel,
    ExperimentVersionModel,
    OutboxModel,
    RunModel,
    RunStageModel,
)
from hydrolab.db.models.identity import (
    AuditLogModel,
    InvitationModel,
    SessionModel,
    ShareLinkModel,
    UserModel,
)
from hydrolab.db.models.results import (
    ExportManifestModel,
    MetricPointModel,
    PlotSpecModel,
    ResultArtifactModel,
    ResultModel,
)

__all__ = [
    "ArtifactModel",
    "AuditLogModel",
    "CheckpointModel",
    "CodeRepositoryModel",
    "CodeVersionModel",
    "DatasetImportJobModel",
    "DatasetModel",
    "DatasetVersionModel",
    "DraftModel",
    "EnvironmentModel",
    "EnvironmentVersionModel",
    "ExperimentModel",
    "ExperimentVersionModel",
    "ExportManifestModel",
    "FieldMappingModel",
    "FolderModel",
    "GpuLeaseModel",
    "InvitationModel",
    "MetricPointModel",
    "OutboxModel",
    "ParameterPresetModel",
    "PlotSpecModel",
    "ResourceSampleModel",
    "ResultArtifactModel",
    "ResultModel",
    "RunEventModel",
    "RunExecutionModel",
    "RunLogChunkModel",
    "RunModel",
    "RunStageModel",
    "SessionModel",
    "ShareLinkModel",
    "TemplateModel",
    "TemplateVersionModel",
    "UserModel",
]
