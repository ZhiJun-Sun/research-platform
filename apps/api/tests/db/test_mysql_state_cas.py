"""MySQL 集成测试：Run 状态 CAS 与终态保护（A9）。

依赖独立测试库（HYDROLAB_TEST_DATABASE_URL）；未配置时整组跳过。
只做新增（建表/插入/更新单行），绝不删除业务数据。
"""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from hydrolab.db.repositories.experiments import (
    SqlExperimentStore,
    SqlExperimentVersionStore,
    SqlRunStore,
)
from hydrolab.db.repositories.identity import SqlUserRepository
from hydrolab.domain.entities import User, utcnow
from hydrolab.experiments.entities import Experiment, ExperimentVersion, Run
from hydrolab.experiments.enums import RunStatus
from hydrolab.experiments.errors import StaleStateError

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
    user = User(email=f"cas-{uuid4().hex}@example.com", display_name="CAS 测试", password_hash="hash")
    await SqlUserRepository(sf).add(user)
    experiment = Experiment(owner_id=user.id, name="CAS 实验")
    await SqlExperimentStore(sf).add(experiment)
    version = ExperimentVersion(
        experiment_id=experiment.id, version_no=1, resolved_config={}, config_hash=uuid4().hex
    )
    await SqlExperimentVersionStore(sf).add(version)
    run = Run(
        experiment_id=experiment.id,
        experiment_version_id=version.id,
        owner_id=user.id,
        idempotency_key=f"cas-{uuid4().hex}",
    )
    await SqlRunStore(sf).add(run)
    return run


async def test_cas_success_forward_transition(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """期望前置状态匹配时，原子 CAS 写入成功。"""
    store = SqlRunStore(session_factory)
    run = await _make_run(session_factory)
    run.status = RunStatus.PREPARING
    run.updated_at = utcnow()
    await store.save(run, expected_status=RunStatus.QUEUED)
    assert (await store.get(run.id)).status == RunStatus.PREPARING


async def test_cas_rejects_wrong_expected_status(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """期望前置状态不匹配时抛 StaleStateError，数据库状态不变。"""
    store = SqlRunStore(session_factory)
    run = await _make_run(session_factory)
    # 当前状态是 QUEUED；期望前置状态写 RUNNING => 不匹配，应拒绝。
    run.status = RunStatus.RUNNING
    run.updated_at = utcnow()
    with pytest.raises(StaleStateError):
        await store.save(run, expected_status=RunStatus.RUNNING)
    assert (await store.get(run.id)).status == RunStatus.QUEUED


async def test_terminal_status_not_overwritten_by_late_write(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Run 进入终态后，迟到的非终态写入被拒绝。"""
    store = SqlRunStore(session_factory)
    run = await _make_run(session_factory)
    run.status = RunStatus.SUCCEEDED
    run.updated_at = utcnow()
    await store.save(run, expected_status=RunStatus.QUEUED)

    # 迟到的 cancel 想把已成功的 Run 改为 CANCELLED：应被终态保护拒绝。
    stale = await store.get(run.id)
    stale.status = RunStatus.CANCELLED
    stale.updated_at = utcnow()
    with pytest.raises(StaleStateError):
        await store.save(stale)
    assert (await store.get(run.id)).status == RunStatus.SUCCEEDED


async def test_terminal_idempotent_rewrite_allowed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """同一终态幂等重写（重复 finalize）被允许，不抛错。"""
    store = SqlRunStore(session_factory)
    run = await _make_run(session_factory)
    run.status = RunStatus.RUNNING
    run.updated_at = utcnow()
    await store.save(run, expected_status=RunStatus.QUEUED)

    run.status = RunStatus.SUCCEEDED
    run.updated_at = utcnow()
    await store.save(run, expected_status=RunStatus.RUNNING)

    # 重复 finalize：当前已 SUCCEEDED，再次写 SUCCEEDED 应幂等放行。
    again = await store.get(run.id)
    again.updated_at = utcnow()
    await store.save(again)
    assert (await store.get(run.id)).status == RunStatus.SUCCEEDED
