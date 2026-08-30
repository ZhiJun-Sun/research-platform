"""B2 数据领域枚举。"""

from enum import StrEnum


class DatasetSourceType(StrEnum):
    UPLOAD = "UPLOAD"
    URL = "URL"
    DERIVE = "DERIVE"


class DatasetVersionStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"


class ImportJobStatus(StrEnum):
    CREATED = "CREATED"
    UPLOADING = "UPLOADING"
    VERIFYING = "VERIFYING"
    PROBING = "PROBING"
    MAPPING_REQUIRED = "MAPPING_REQUIRED"
    FINALIZING = "FINALIZING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


class DataFormat(StrEnum):
    CSV = "CSV"
    PARQUET = "PARQUET"
    NETCDF = "NETCDF"
    DIRECTORY = "DIRECTORY"
    UNKNOWN = "UNKNOWN"


class FieldSemantic(StrEnum):
    TIME = "TIME"
    TARGET = "TARGET"
    FEATURE = "FEATURE"
    BASIN_ID = "BASIN_ID"
    STATIC_ATTRIBUTE = "STATIC_ATTRIBUTE"
    IGNORE = "IGNORE"


class ArtifactStatus(StrEnum):
    PENDING_UPLOAD = "PENDING_UPLOAD"
    READY = "READY"
    QUARANTINED = "QUARANTINED"


class ArtifactKind(StrEnum):
    DATASET_SOURCE = "DATASET_SOURCE"
    DATASET_MANIFEST = "DATASET_MANIFEST"
