"""启动时自动执行数据库迁移。

规则（plans/02 第 10 节）：禁止 create_all；所有 schema 变更必须走 Alembic 迁移。
database_backend=mysql 时在应用启动前执行 `alembic upgrade head`，保证 schema 最新。
"""

from pathlib import Path

from alembic import command
from alembic.config import Config

from hydrolab.core.settings import Settings

_API_DIR = Path(__file__).resolve().parents[3]  # apps/api
_ALEMBIC_INI = _API_DIR / "alembic.ini"
_SCRIPT_LOCATION = _API_DIR / "alembic"


def _alembic_config() -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_SCRIPT_LOCATION))
    return cfg


def run_migrations(settings: Settings) -> None:
    """同步执行迁移到 head。使用 pymysql 同步连接（见 alembic/env.py 的 DSN 转换）。"""
    command.upgrade(_alembic_config(), "head")


def current_revision(settings: Settings) -> str | None:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config())
    heads = script.get_heads()
    return heads[0] if heads else None
