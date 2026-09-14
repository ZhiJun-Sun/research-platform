"""add unique constraint on experiment_versions(experiment_id, version_no)

同一实验下 version_no 必须唯一。next_version_no 用 MAX+1 并发分配时可能拿到同一
序号，MySQL 唯一约束是并发竞争的最后兜底（A4）。

Revision ID: c0a111a2f3
Revises: c0a111a2f2
Create Date: 2026-09-14 01:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = 'c0a111a2f3'
down_revision: str | Sequence[str] | None = 'c0a111a2f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_experiment_versions_experiment_id_version_no',
        'experiment_versions',
        ['experiment_id', 'version_no'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_experiment_versions_experiment_id_version_no', 'experiment_versions', type_='unique'
    )