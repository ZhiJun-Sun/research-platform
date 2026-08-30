"""baseline: 空基线，标记迁移链起点。

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-29

业务表从 B1（身份/邀请/授权）开始按领域分批添加，
禁止启动时自动 create_all（plans/02 第 10 节）。
"""

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 空基线：仅建立迁移链起点。
    pass


def downgrade() -> None:
    pass
