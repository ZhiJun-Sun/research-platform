"""Alembic 环境配置。

规则（plans/02 第 10 节）：
- 禁止启动时自动 create_all；所有 schema 变化必须走迁移；
- DATABASE_URL 来自 HYDROLAB_DATABASE_URL 环境变量；
- 未配置时给出明确错误，不静默退化。
"""

import os
from logging.config import fileConfig

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("HYDROLAB_DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "HYDROLAB_DATABASE_URL 未配置；Alembic 需要显式的数据库连接，"
        "禁止使用默认值或启动时自动建表。"
    )
config.set_main_option("sqlalchemy.url", database_url)

# B1 起将逐步注册领域 metadata：
# from hydrolab.db.base import Base
# target_metadata = Base.metadata
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import engine_from_config, pool

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
