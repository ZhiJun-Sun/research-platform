"""normalize dataset_versions collation for databases already at b32a91f9c7d4

有些库已在 b32a91f9c7d4（外键已建），但仍带 utf8mb4_unicode_ci 的
dataset_versions。由于 c0a111a2f1 是 b32a91f9c7d4 的祖先，对这些库不会重放。
本迁移幂等地把 dataset_versions 对齐到服务器默认 collation，是面向
「已停在 b32a91f9c7d4」旧库的独立升级路径。对全新库此操作是幂等 no-op。

Revision ID: c0a111a2f2
Revises: b32a91f9c7d4
Create Date: 2026-09-14 00:21:00.000000
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = 'c0a111a2f2'
down_revision: str | Sequence[str] | None = 'b32a91f9c7d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _target_collation() -> str:
    """取 datasets.id 的 collation；找不到时回退服务器默认。"""
    bind = op.get_bind()
    db = bind.execute(text("SELECT DATABASE()")).scalar()
    row = bind.execute(
        text(
            "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'datasets' AND COLUMN_NAME = 'id'"
        ),
        {"db": db},
    ).fetchone()
    if row and row[0]:
        return row[0]
    return bind.execute(text("SELECT @@collation_server")).scalar()


def _table_collation() -> str | None:
    bind = op.get_bind()
    db = bind.execute(text("SELECT DATABASE()")).scalar()
    row = bind.execute(
        text(
            "SELECT TABLE_COLLATION FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'dataset_versions'"
        ),
        {"db": db},
    ).fetchone()
    return row[0] if row else None


def upgrade() -> None:
    target = _target_collation()
    current = _table_collation()
    if current == target:
        return
    op.execute(
        f"ALTER TABLE dataset_versions CONVERT TO CHARACTER SET utf8mb4 COLLATE {target}"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE dataset_versions CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
