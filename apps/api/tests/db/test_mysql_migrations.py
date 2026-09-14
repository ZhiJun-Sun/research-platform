"""MySQL 集成测试：Alembic 迁移升级与 schema 断言。

仅在配置了 HYDROLAB_TEST_DATABASE_URL 时执行（指向一个可重建的测试库）；
未配置时整组跳过，保证无数据库的 CI/本地开发仍可运行。

安全约束：对数据库只做【新增】（建库/建表/升级迁移），
绝不执行删除数据库或表操作（不做 downgrade 落地执行）。
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

TEST_DATABASE_URL = os.environ.get("HYDROLAB_TEST_DATABASE_URL")
_SYNC_URL = (
    TEST_DATABASE_URL.replace("mysql+asyncmy", "mysql+pymysql") if TEST_DATABASE_URL else None
)
_API_DIR = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    cfg = Config(str(_API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_API_DIR / "alembic"))
    return cfg


def _sync_engine():
    return create_engine(_SYNC_URL, poolclass=None)


pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="HYDROLAB_TEST_DATABASE_URL 未配置（需要真实 MySQL 测试库）"
)


@pytest.fixture(scope="module", autouse=True)
def _database_environment() -> Iterator[str]:
    """迁移期间给 Alembic 提供 HYDROLAB_DATABASE_URL；结束后恢复。"""
    old = os.environ.get("HYDROLAB_DATABASE_URL")
    os.environ["HYDROLAB_DATABASE_URL"] = TEST_DATABASE_URL
    try:
        yield TEST_DATABASE_URL
    finally:
        if old is None:
            os.environ.pop("HYDROLAB_DATABASE_URL", None)
        else:
            os.environ["HYDROLAB_DATABASE_URL"] = old


@pytest.fixture(scope="module", autouse=True)
def _reset_schema():
    """只执行 upgrade head（新增表/约束），不 downgrade、不删除任何数据。"""
    command.upgrade(_alembic_config(), "head")
    yield


def test_migration_upgrade_is_idempotent() -> None:
    """重复 upgrade head 不报错（幂等），证明迁移脚本可安全重放。"""
    command.upgrade(_alembic_config(), "head")
    command.upgrade(_alembic_config(), "head")


def test_downgrade_sql_generates_without_executing() -> None:
    """离线生成 downgrade SQL 文本（--sql 模式不连库、不落地执行），
    验证降级脚本语法正确，同时遵守“不对数据库执行删除”的安全约束。"""
    import subprocess

    env = {**os.environ, "HYDROLAB_DATABASE_URL": TEST_DATABASE_URL}
    # 离线生成从 head 降到基线的 SQL（--sql 不连库、不落地执行）
    result = subprocess.run(
        [os.sys.executable, "-m", "alembic", "downgrade", "b32a91f9c7d4:0001_baseline", "--sql"],
        cwd=str(_API_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "DROP TABLE" in result.stdout, "离线 downgrade SQL 应包含 DROP TABLE 语句"


def test_all_business_tables_exist() -> None:
    engine = _sync_engine()
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        expected = {
            "users",
            "invitations",
            "sessions",
            "resource_grants",
            "share_links",
            "audit_logs",
            "asset_folders",
            "datasets",
            "dataset_versions",
            "artifacts",
            "field_mappings",
            "dataset_import_jobs",
            "code_repositories",
            "code_versions",
            "experiment_templates",
            "template_versions",
            "runtime_environments",
            "environment_versions",
            "parameter_presets",
            "experiment_drafts",
            "experiments",
            "experiment_versions",
            "runs",
            "run_stages",
            "outbox_events",
            "gpu_leases",
            "run_executions",
            "run_events",
            "run_logs",
            "resource_samples",
            "checkpoints",
            "results",
            "metric_points",
            "result_artifacts",
            "plot_specs",
            "export_manifests",
        }
        missing = expected - tables
        assert not missing, f"缺少表: {sorted(missing)}"
    finally:
        engine.dispose()


def test_foreign_keys_are_created() -> None:
    """验证第二段迁移（外键 + 幂等唯一约束）真实落地。"""
    engine = _sync_engine()
    try:
        inspector = inspect(engine)
        # runs 引用的外键
        runs_fks = {
            (fk["referred_table"], tuple(sorted(fk["constrained_columns"])))
            for fk in inspector.get_foreign_keys("runs")
        }
        assert ("experiments", ("experiment_id",)) in runs_fks
        assert ("experiment_versions", ("experiment_version_id",)) in runs_fks
        assert ("users", ("owner_id",)) in runs_fks
        # 子表引用 runs
        stage_fks = inspector.get_foreign_keys("run_stages")
        assert any(fk["referred_table"] == "runs" and fk["constrained_columns"] == ["run_id"] for fk in stage_fks)
        events_fks = inspector.get_foreign_keys("run_events")
        assert any(fk["referred_table"] == "runs" and fk["constrained_columns"] == ["run_id"] for fk in events_fks)
        # results / metric_points
        results_fks = inspector.get_foreign_keys("results")
        assert any(fk["referred_table"] == "runs" for fk in results_fks)
        metrics_fks = inspector.get_foreign_keys("metric_points")
        assert any(fk["referred_table"] == "results" for fk in metrics_fks)
    finally:
        engine.dispose()


def test_run_idempotency_unique_constraint_exists() -> None:
    engine = _sync_engine()
    try:
        inspector = inspect(engine)
        runs_unique = set()
        for c in inspector.get_unique_constraints("runs"):
            runs_unique.add(tuple(sorted(c["column_names"])))
        assert ("idempotency_key", "owner_id") in runs_unique, f"缺少幂等唯一约束: {runs_unique}"
    finally:
        engine.dispose()


def test_gpu_lease_unique_gpu_index_exists() -> None:
    engine = _sync_engine()
    try:
        inspector = inspect(engine)
        leases_unique = set()
        for c in inspector.get_unique_constraints("gpu_leases"):
            leases_unique.add(tuple(sorted(c["column_names"])))
        assert ("gpu_index",) in leases_unique, f"gpu_leases 缺少 gpu_index 唯一约束: {leases_unique}"
    finally:
        engine.dispose()
