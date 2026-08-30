"""B4 实验与 Run 状态枚举。"""

from enum import StrEnum


class DraftStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUBMITTED = "SUBMITTED"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunStageName(StrEnum):
    TRAINING = "TRAINING"
    EVALUATING = "EVALUATING"
    PLOTTING = "PLOTTING"
    UPLOADING = "UPLOADING"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
