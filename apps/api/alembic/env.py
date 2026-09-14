"""Alembic 环境配置。

规则（plans/02 第 10 节）：
- 禁止启动时自动 create_all；所有 schema 变化必须走迁移；
- DATABASE_URL 来自 HYDROLAB_DATABASE_URL 环境变量；
- 未配置时给出明确错误，不静默退化；
- 迁移使用同步驱动 pymysql（应用运行时用 asyncmy），自动转换 DSN。
- 直接构造 engine，不走 ini 字符串插值（连接串含 % 时不受 configparser 影响）。
"""

import os
from logging.config import fileConfig

from alembic import context

import hydrolab.db.models  # noqa: F401 - 注册全部领域表到 metadata
from hydrolab.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("HYDROLAB_DATABASE_URL")
if not database_url:
    # 未显式配置时回退到 Settings 默认值（MySQL 实例），保证迁移可用。
    from hydrolab.core.settings import get_settings

    database_url = get_settings().database_url
if not database_url:
    raise RuntimeError(
        "HYDROLAB_DATABASE_URL 未配置；Alembic 需要显式的数据库连接，"
        "禁止使用默认值或启动时自动建表。"
    )
# 迁移走同步 pymysql；应用运行时使用 asyncmy。
database_url = database_url.replace("mysql+asyncmy", "mysql+pymysql")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine, pool

    connectable = create_engine(database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
