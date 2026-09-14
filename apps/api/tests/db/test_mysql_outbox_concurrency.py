"""MySQL 集成测试：Outbox 发布者并发语义（A5）。

验证跨两个连接的领取/SKIP LOCKED、领取过期重领、旧领取迟到确认被拒收。
broker（Celery/Redis 队列）无本地服务，enqueue 行为由既有 mock/single 测试覆盖；
这里只测真实 DB 侧的并发原子性。依赖独立测试库；未配置时整组跳过。
"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from hydrolab.db.repositories.experiments import SqlOutboxStore
from hydrolab.domain.entities import utcnow
from hydrolab.experiments.entities import OutboxEvent
from hydrolab.experiments.enums import OutboxStatus

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
    from sqlalchemy import create_engine, text

    old = os.environ.get("HYDROLAB_DATABASE_URL")
    os.environ["HYDROLAB_DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(_alembic_config(), "head")
    engine = create_engine(TEST_DATABASE_URL.replace("mysql+asyncmy", "mysql+pymysql"))
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM outbox_events"))
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


async def _add_event(sf: async_sessionmaker[AsyncSession], topic: str = "run.requested") -> OutboxEvent:
    event = OutboxEvent(
        aggregate_type="RUN", aggregate_id=uuid4(), topic=topic, payload={"run_id": str(uuid4())}
    )
    await SqlOutboxStore(sf).add(event)
    return event


async def test_two_claimers_claim_disjoint_events(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """两个发布者实例并发领取：每个事件至多被领一次（SKIP LOCKED）。"""
    await _add_event(session_factory)
    await _add_event(session_factory)
    store = SqlOutboxStore(session_factory)

    claimed_a, claimed_b = await asyncio.gather(
        store.claim_pending(limit=1), store.claim_pending(limit=1)
    )
    all_claimed = claimed_a + claimed_b
    # 共两个事件，各被领一次，无重复。
    assert len(all_claimed) == 2, f"应恰好领到 2 个事件，实际 {len(all_claimed)}"
    ids = [e.id for e in all_claimed]
    assert len(set(ids)) == 2, "同一事件不应被两个实例重复领取"


async def test_stale_claim_can_be_reclaimed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """发布者崩溃遗留的 PUBLISHING 事件（超过 300 秒）可被重新领取。"""
    store = SqlOutboxStore(session_factory)
    event = await _add_event(session_factory)
    # 手动造一个「已领取但超时未确认」的 PUBLISHING 记录。
    from sqlalchemy import text

    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE outbox_events SET status='PUBLISHING', "
                "published_at = NOW() - INTERVAL 600 SECOND WHERE id = :id"
            ),
            {"id": event.id},
        )
        await s.commit()

    claimed = await store.claim_pending(limit=10)
    assert any(e.id == event.id for e in claimed), "超时 PUBLISHING 事件应被重新领取"
    for e in claimed:
        if e.id == event.id:
            assert e.status == OutboxStatus.PUBLISHING
            ranked = e.published_at
            assert ranked is not None
    # 重新领取后，旧 claimed_at 无法确认（迟到投递被拒收）。
    stale = await store.mark_published(event.id, utcnow(), utcnow() - timedelta(seconds=1))
    assert stale is None, "旧领取的迟到确认必须被拒收"


async def test_late_confirm_with_wrong_claimed_at_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """只有持有正确 claimed_at 的领取者能 confirm，旧领取不能覆盖新领取。"""
    store = SqlOutboxStore(session_factory)
    event = await _add_event(session_factory)
    claimed = await store.claim_pending(limit=1)
    assert len(claimed) == 1
    claimed[0].status = OutboxStatus.PUBLISHING
    stamped = claimed[0]

    wrong = await store.mark_published(event.id, utcnow(), utcnow() - timedelta(seconds=30))
    assert wrong is None, "claimed_at 不匹配的确认必须被拒收"
    right = await store.mark_published(event.id, utcnow(), stamped.published_at)
    assert right is not None, "持正确 claimed_at 的确认应成功"
    assert right.status == OutboxStatus.PUBLISHED