"""normalize dataset_versions collation before FK creation

初始迁移把 dataset_versions 硬编码为 utf8mb4_unicode_ci，而它引用的 datasets.id
等列可能是服务器默认（utf8mb4_0900_ai_ci）或别的 collation。两者不一致导致
b32a91f9c7d4 里对 dataset_versions 建外键时抛 3780
(Referencing column 'dataset_id' and referenced column 'id' ... are incompatible)。

本迁移必须在 b32a91f9c7d4（建外键）之前执行。目标 collation 取「引用表
datasets.id 的 collation」，而不是盲目用服务器默认：因为外键要求两边一致，
只有对齐被引用列才能让 FK 成功，同时兼容全新库（datasets.id=服务器默认）
与混合 collation 的旧库（datasets.id=utf8mb4_unicode_ci）。不修改初始脚本。

Revision ID: c0a111a2f1
Revises: 4e409406eb80
Create Date: 2026-09-14 00:20:00.000000
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = 'c0a111a2f1'
down_revision: str | Sequence[str] | None = '4e409406eb80'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _target_collation() -> str:
    """取 datasets.id 的 collation（外键兼容的依据）；找不到时回退服务器默认。"""
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


def upgrade() -> None:
    target = _target_collation()
    op.execute(
        f"ALTER TABLE dataset_versions CONVERT TO CHARACTER SET utf8mb4 COLLATE {target}"
    )


def downgrade() -> None:
    # 恢复到初始迁移设定的 utf8mb4_unicode_ci，保证降级链路与初始脚本一致。
    op.execute(
        "ALTER TABLE dataset_versions CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
