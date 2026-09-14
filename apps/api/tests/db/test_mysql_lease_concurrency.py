"""MySQL 集成测试：GPU 租约并发与死锁重试（A8）。

依赖独立测试库；未配置时整组跳过。只做新增（建表/插入），不删业务数据。
"""

import os
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from hydrolab.db.repositories.execution import SqlGpuLeases
from hydrolab.db.repositories.experiments import (
    SqlExperimentStore,
    SqlExperimentVersionStore,
    SqlRunStore,
)
from hydrolab.db.repositories.identity import SqlUserRepository
from hydrolab.domain.entities import User, utcnow
from hydrolab.experiments.entities import Experiment, ExperimentVersion, Run

TEST_DATABASE_URL = os.environ.get("HYDROLAB_TEST_DATABASE_URL")
ASYNC_URL = TEST_DATABASE_URL.replace("mysql+pymysql", "mysql+asyncmy") if TEST_DATABASE_URL else None
API_DIR = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="HYDROLAB_TEST_DATABASE_URL 未配置（需要真实 MySQL 测试库）"
)


def _alembic_config() -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    return cfg


@pytest.fixture(scope="module", autouse=True)
def _database_environment() -> Iterator[str]:
    old = os.environ.get("HYDROLAB_DATABASE_URL")
    os.environ["HYDROLAB_DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(_alembic_config(), "head")
    # gpu_leases 以固定小整数 gpu_index 为主键，跨多次 pytest 运行会在持久测试库中累积
    # 占用；这里只清空本测试模块关心的叶子表（无下游引用），保证并发测试幂等可重复。
    # 不删除业务表，也不删除 runs/experiments 等有业务含义的数据。
    engine = create_engine(TEST_DATABASE_URL.replace("mysql+asyncmy", "mysql+pymysql"))
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM gpu_leases"))
    finally:
        engine.dispose()
    try:
        yield TEST_DATABASE_URL
    finally:
        if old is None:
            os.environ.pop("HYDROLAB_DATABASE_URL", None)
        else:
            os.environ["HYDROLAB_DATABASE_URL"] = old


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(ASYNC_URL, poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _make_run(sf: async_sessionmaker[AsyncSession]) -> Run:
    user = User(email=f"lease-{uuid4().hex}@example.com", display_name="租约测试", password_hash="hash")
    await SqlUserRepository(sf).add(user)
    experiment = Experiment(owner_id=user.id, name="租约实验")
    await SqlExperimentStore(sf).add(experiment)
    version = ExperimentVersion(
        experiment_id=experiment.id, version_no=1, resolved_config={}, config_hash=uuid4().hex
    )
    await SqlExperimentVersionStore(sf).add(version)
    run = Run(
        experiment_id=experiment.id,
        experiment_version_id=version.id,
        owner_id=user.id,
        idempotency_key=f"lease-{uuid4().hex}",
    )
    await SqlRunStore(sf).add(run)
    return run


async def test_two_connections_contend_for_single_gpu(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """两个连接同时抢同一张 GPU：恰好一个拿到，另一个返回空，无 500/无死锁。"""
    import asyncio

    run_a = await _make_run(session_factory)
    run_b = await _make_run(session_factory)
    leases_store = SqlGpuLeases(session_factory, gpu_count=1)
    expires = utcnow() + timedelta(minutes=2)

    results = await asyncio.gather(
        leases_store.acquire(run_a.id, 1, expires),
        leases_store.acquire(run_b.id, 1, expires),
    )
    winners = [leases for leases in results if leases]
    assert len(winners) == 1, f"应恰好一个连接拿到租约，实际 {[len(x) for x in results]}"
    # 只有一个 gpu_index 被占用
    assert len(await leases_store.list_by_run(winners[0][0].run_id)) == 1
    await leases_store.release_run(winners[0][0].run_id)


def test_deadlock_error_detection() -> None:
    """OperationalError 死锁/锁等待超时能被识别为可重试。"""
    from pymysql.err import OperationalError as PyOperationalError

    exc = OperationalError("stmt", {}, PyOperationalError(1213, "Deadlock found"))
    assert SqlGpuLeases._is_deadlock(exc)

    timeout = OperationalError("stmt", {}, PyOperationalError(1205, "Lock wait timeout"))
    assert SqlGpuLeases._is_deadlock(timeout)

    other = OperationalError("stmt", {}, PyOperationalError(1045, "Access denied"))
    assert not SqlGpuLeases._is_deadlock(other)


async def test_acquire_retries_deadlock_then_succeeds(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """死锁重试路径：模拟两次死锁后成功，验证重试逻辑收敛。"""
    from pymysql.err import OperationalError as PyOperationalError

    class FlakyGpuLeases(SqlGpuLeases):
        def __init__(self) -> None:
            super().__init__(session_factory, gpu_count=1, max_deadlock_retries=3)
            self.calls = 0

        async def _acquire_once(self, run_id, count, expires_at):
            self.calls += 1
            if self.calls <= 2:
                raise OperationalError("stmt", {}, PyOperationalError(1213, "Deadlock found"))
            return await super()._acquire_once(run_id, count, expires_at)

    run = await _make_run(session_factory)
    store = FlakyGpuLeases()
    leases = await store.acquire(run.id, 1, utcnow() + timedelta(minutes=2))
    assert len(leases) == 1
    assert store.calls == 3
