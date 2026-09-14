"""MySQL 异步引擎与会话工厂。

由 Settings 提供连接串；仅在 database_backend=mysql 时使用。
引擎按 database_url 惰性缓存，避免无库测试导入时触发连接。
dispose 时释放所有已创建引擎（供应用关闭时清理连接池）。
"""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from hydrolab.core.settings import Settings, get_settings

_created_async: set[AsyncEngine] = set()
_created_sync: set[Engine] = set()


def _make_async_engine(url: str) -> AsyncEngine:
    engine = create_async_engine(url, pool_pre_ping=True, pool_recycle=1800)
    _created_async.add(engine)
    return engine


def _make_sync_engine(url: str) -> Engine:
    sync_url = url.replace("mysql+asyncmy", "mysql+pymysql")
    engine = create_engine(sync_url, poolclass=NullPool)
    _created_sync.add(engine)
    return engine


@lru_cache
def get_session_factory() -> async_sessionmaker:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("database_backend=mysql 但未配置 database_url")
    engine = _make_async_engine(settings.database_url)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def make_session_factory(settings: Settings) -> async_sessionmaker:
    if not settings.database_url:
        raise RuntimeError("database_backend=mysql 但未配置 database_url")
    engine = _make_async_engine(settings.database_url)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def sync_engine_for_migrations(settings: Settings) -> Engine:
    if not settings.database_url:
        raise RuntimeError("未配置 database_url")
    return _make_sync_engine(settings.database_url)


async def dispose() -> None:
    """关闭所有已创建引擎，释放连接池。供应用关闭时调用。"""
    for engine in list(_created_async):
        await engine.dispose()
    _created_async.clear()
    for engine in list(_created_sync):
        engine.dispose()
    _created_sync.clear()
    get_session_factory.cache_clear()