"""MySQL 集成测试：提交原子性（A3）与并发幂等（A4）。

验证在唯一约束冲突（IntegrityError）时 UnitOfWork 整体回滚，不残留多余的
Experiment/Version；并发同 owner+key 提交只收敛到一个 Run。
依赖独立测试库；未配置时整组跳过。只做新增（建表/插入），不删业务数据。
"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from hydrolab.db.repositories.experiments import (
    SqlExperimentStore,
    SqlExperimentVersionStore,
    SqlRunStageStore,
    SqlRunStore,
)
from hydrolab.db.repositories.identity import SqlGrantRepository, SqlUserRepository
from hydrolab.db.unit_of_work import UnitOfWork
from hydrolab.domain.entities import ResourceGrant, User
from hydrolab.domain.enums import ResourceType, Role
from hydrolab.experiments.entities import Experiment, ExperimentVersion, Run, RunStage
from hydrolab.experiments.enums import RunStageName

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


async def _make_user(sf: async_sessionmaker[AsyncSession]) -> User:
    user = User(email=f"uow-{uuid4().hex}@example.com", display_name="UoW 测试", password_hash="hash")
    await SqlUserRepository(sf).add(user)
    return user


async def _submit_write_path(
    sf: async_sessionmaker[AsyncSession],
    user: User,
    key: str,
    uow: UnitOfWork,
) -> Run:
    """复现 ExperimentService.submit 的写路径：在同一个 UoW 内建实验/版本/Run/阶段。"""
    async with uow:
        experiment = await SqlExperimentStore(sf).add(
            Experiment(owner_id=user.id, name=f"UoW {key}")
        )
        await SqlGrantRepository(sf).add(
            ResourceGrant(
                resource_type=ResourceType.EXPERIMENT,
                resource_id=experiment.id,
                subject_id=user.id,
                role=Role.OWNER,
                granted_by=user.id,
            )
        )
        version = await SqlExperimentVersionStore(sf).add(
            ExperimentVersion(
                experiment_id=experiment.id, version_no=1, resolved_config={}, config_hash=uuid4().hex
            )
        )
        run = await SqlRunStore(sf).add(
            Run(
                experiment_id=experiment.id,
                experiment_version_id=version.id,
                owner_id=user.id,
                idempotency_key=key,
            )
        )
        for position, name in enumerate(RunStageName):
            await SqlRunStageStore(sf).add(RunStage(run_id=run.id, name=name, position=position))
        return run


async def test_uow_commits_atomically(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """一次提交全部落地：实验、grant、版本、Run、阶段都在同一事务内持久化。"""
    user = await _make_user(session_factory)
    run = await _submit_write_path(
        session_factory, user, f"k-{uuid4().hex}", UnitOfWork(session_factory)
    )
    assert (await SqlRunStore(session_factory).get(run.id)) is not None
    assert (await SqlExperimentStore(session_factory).get(run.experiment_id)) is not None
    assert (await SqlRunStageStore(session_factory).list_by_run(run.id)) != []


async def test_duplicate_key_rolls_back_entire_tx(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """同 owner+key 冲突时，UnitOfWork 整体回滚，不残留多余 Experiment/Version/Run。"""
    user = await _make_user(session_factory)
    key = f"dup-{uuid4().hex}"
    first = await _submit_write_path(session_factory, user, key, UnitOfWork(session_factory))

    # 第二次用同一 key 提交：在 run 插入时触发唯一约束，整个事务回滚。
    with pytest.raises(IntegrityError):
        await _submit_write_path(session_factory, user, key, UnitOfWork(session_factory))

    # 结果只有一个 Run / 一个 Experiment（失败的写入被整体回滚，无残留）。
    runs = await SqlRunStore(session_factory).list_by_owner(user.id)
    assert len(runs) == 1, f"应只存在一个 Run，实际 {len(runs)}"
    assert runs[0].id == first.id
    experiments = await SqlExperimentStore(session_factory).list_by_owner(user.id)
    assert len(experiments) == 1, f"应只存在一个 Experiment，实际 {len(experiments)}"
    assert experiments[0].id == first.experiment_id


async def test_concurrent_same_key_converges_to_one_run(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """两个并发提交同 owner+key：恰好一个落库，另一个因唯一约束回滚。"""
    user = await _make_user(session_factory)
    key = f"conc-{uuid4().hex}"

    async def _submit_attempt() -> Run:
        return await _submit_write_path(session_factory, user, key, UnitOfWork(session_factory))

    results = await asyncio.gather(_submit_attempt(), _submit_attempt(), return_exceptions=True)
    successes = [r for r in results if isinstance(r, Run)]
    failures = [r for r in results if not isinstance(r, Run)]
    assert len(successes) == 1, f"应恰好一个成功，实际 {len(successes)}: {failures}"
    # 失败方是因唯一约束冲突回滚（IntegrityError），不是其它错误。
    assert all(isinstance(f, IntegrityError) for f in failures)

    runs = await SqlRunStore(session_factory).list_by_owner(user.id)
    assert len(runs) == 1
    assert runs[0].id == successes[0].id
    experiments = await SqlExperimentStore(session_factory).list_by_owner(user.id)
    assert len(experiments) == 1, "并发失败方不应残留多余 Experiment"
