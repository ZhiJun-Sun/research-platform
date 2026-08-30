"""B3 代码、模板和运行环境领域枚举。"""

from enum import StrEnum


class CodeSourceType(StrEnum):
    ZIP = "ZIP"
    GIT = "GIT"


class CodeVersionStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"


class TemplateMode(StrEnum):
    TRAIN = "TRAIN"
    EVALUATE = "EVALUATE"
    PREDICT = "PREDICT"


class EnvironmentStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    FAILED = "FAILED"


class ParameterType(StrEnum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    SELECT = "SELECT"
