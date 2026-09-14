"""MySQL SQL 仓储集成测试。

测试只在 HYDROLAB_TEST_DATABASE_URL 配置时执行，且要求该 URL 指向独立测试库。
安全约束：只做【新增】（建表/插入），绝不删除数据库或表。
"""

import os
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from hydrolab.db.repositories.experiments import SqlExperimentStore, SqlExperimentVersionStore, SqlRunStore
from hydrolab.db.repositories.identity import SqlInvitationRepository, SqlUserRepository
from hydrolab.domain.entities import Invitation, User, utcnow
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
    """只执行 upgrade head（建表），不 downgrade、不删除任何数据。"""
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


async def test_sql_identity_repository_roundtrip(session_factory: async_sessionmaker[AsyncSession]) -> None:
    repository = SqlUserRepository(session_factory)
    user = User(email=f"sql-{uuid4().hex}@example.com", display_name="SQL 测试用户", password_hash="hash")

    await repository.add(user)

    loaded = await repository.get(user.id)
    assert loaded is not None
    assert loaded.id == user.id
    assert loaded.email == user.email
    assert await repository.get_by_email(user.email) is not None


async def test_sql_foreign_key_rejects_unknown_inviter(session_factory: async_sessionmaker[AsyncSession]) -> None:
    repository = SqlInvitationRepository(session_factory)
    invitation = Invitation(
        token_hash=f"token-{uuid4().hex}",
        email="unknown@example.com",
        inviter_id=uuid4(),
        expires_at=utcnow() + timedelta(days=1),
    )

    with pytest.raises(IntegrityError):
        await repository.add(invitation)


async def test_sql_run_idempotency_is_unique_per_owner(session_factory: async_sessionmaker[AsyncSession]) -> None:
    user = User(email=f"run-{uuid4().hex}@example.com", display_name="Run 测试用户", password_hash="hash")
    await SqlUserRepository(session_factory).add(user)

    experiment = Experiment(owner_id=user.id, name="SQL 实验")
    await SqlExperimentStore(session_factory).add(experiment)
    version = ExperimentVersion(
        experiment_id=experiment.id,
        version_no=1,
        resolved_config={},
        config_hash=uuid4().hex,
    )
    await SqlExperimentVersionStore(session_factory).add(version)

    repository = SqlRunStore(session_factory)
    first = Run(
        experiment_id=experiment.id,
        experiment_version_id=version.id,
        owner_id=user.id,
        idempotency_key="same-submit",
    )
    await repository.add(first)
    assert (await repository.get_by_idempotency(user.id, "same-submit")).id == first.id

    duplicate = Run(
        experiment_id=experiment.id,
        experiment_version_id=version.id,
        owner_id=user.id,
        idempotency_key="same-submit",
    )
    with pytest.raises(IntegrityError):
        await repository.add(duplicate)
