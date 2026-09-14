"""共享事务 / UnitOfWork 支持（A3）。

仓储默认每个方法各自打开 session 并提交。调用方可用 :class:`UnitOfWork`
把一个 session 绑定到 contextvar，使作用域内的仓储方法共用同一事务：
要么全部成功一起提交，要么全部回滚。

未绑定任何 UnitOfWork 时，``session_scope`` 与 ``commit_or_defer`` 完全复现
原先「每个方法各自提交」的语义，因此默认路径零行为变化。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from types import TracebackType
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_current_session: ContextVar[AsyncSession | None] = ContextVar("hydrolab_uow_session", default=None)


class UnitOfWork:
    """把单个 session 绑定到当前任务，退出时统一提交或回滚。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory
        self.session: AsyncSession | None = None
        self._token: Any | None = None

    async def __aenter__(self) -> AsyncSession:
        session = self._sf()
        self.session = session
        self._token = _current_session.set(session)
        return session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self.session is not None
        assert self._token is not None
        _current_session.reset(self._token)
        try:
            if exc_type is None:
                await self.session.commit()
            else:
                await self.session.rollback()
        finally:
            await self.session.close()
            self.session = None
            self._token = None


@asynccontextmanager
async def session_scope(sf: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """提供仓库内部使用的 session。

    处于 UnitOfWork 中时返回被绑定的共享 session（由 UoW 管理生命周期）；
    否则打开一个新 session，结束后关闭。
    """
    bound = _current_session.get()
    if bound is not None:
        yield bound
        return
    session = sf()
    try:
        yield session
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()


async def commit_or_defer(session: AsyncSession) -> None:
    """未处于 UnitOfWork 时立即提交；处于 UoW 时延迟到其退出时统一提交。"""
    if _current_session.get() is None:
        await session.commit()
