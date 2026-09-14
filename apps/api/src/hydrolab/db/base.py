"""SQLAlchemy 声明式基类与公共列/类型。

- 所有业务表使用 UUID 主键、UTC 时间戳，与领域实体规则一致（plans/02 第 3 节）。
- MySQL 无原生 UUID/JSON 语义差异由 SQLAlchemy 类型层屏蔽。
- 类型均以模块级命名类导出，使 Alembic autogenerate 生成的迁移可独立导入执行。
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import CHAR, JSON, DateTime, TypeDecorator
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """应用声明式基类。Alembic 使用 Base.metadata 作为 target_metadata。"""


class UUID36(TypeDecorator[UUID]):
    """MySQL 上的 UUID 列：存 CHAR(36)，读写自动转换 Python uuid.UUID 对象。"""

    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value: UUID | None, dialect) -> str | None:
        return str(value) if value is not None else None

    def process_result_value(self, value: str | None, dialect) -> UUID | None:
        return UUID(value) if value is not None else None


class UTCDateTime(TypeDecorator[datetime]):
    """存储 naive UTC，返回时标记 UTC，避免 MySQL DATETIME 无时区信息导致偏移错误。"""

    impl = DateTime()
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


def uuid_column(**kwargs):
    """UUID 主键/外键列的快捷构造（存 CHAR(36)，返回 UUID 对象）。"""
    return UUID36(**kwargs)


def json_column(**kwargs):
    """MySQL JSON 列，映射领域实体的 dict/list 聚合字段。nullable 由调用方 mapped_column 控制。"""
    return JSON(**kwargs)