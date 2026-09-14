"""Alembic 迁移前置核查：检测 dataset_versions 与服务器默认 collation 是否一致。

在升级任何疑似旧库前，用本模块只读检查目标库的 collation 状态，避免在
collation 不一致时盲目升级（MySQL 可能因 3780 建外键失败）。

只读：只执行 SELECT / information_schema 查询，不修改任何数据。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CollationIssue:
    table: str
    column: str | None
    actual: str
    expected: str


@dataclass(frozen=True)
class CollationCheckResult:
    server_collation: str
    issues: list[CollationIssue]

    @property
    def ok(self) -> bool:
        # 退出/通过只由「外键相关跨表不一致」决定；与服务器默认的差异仅作参考，
        # 因为整个 schema 可能合法地统一使用与服务器默认不同的 collation。
        return not self.issues


def check_collation_consistency(database_url: str) -> CollationCheckResult:
    """连接目标库并核对 dataset_versions 与它引用的 datasets.id 的 collation 一致。

    dataset_versions 与外键关联的 datasets.id 必须 collation 相同，否则
    b32a91f9c7d4 建外键会抛 MySQL 3780。这里以 datasets.id 为基准做跨表核验；
    同时报告服务器默认 collation 供参考。database_url 可为 pymysql/asyncmy DSN，
    内部用同步 pymysql 驱动只读探测。
    """
    from sqlalchemy import create_engine, text

    url = database_url.replace("mysql+asyncmy", "mysql+pymysql")
    engine = create_engine(url, pool_pre_ping=True)
    issues: list[CollationIssue] = []
    try:
        with engine.connect() as conn:
            server_collation = conn.execute(text("SELECT @@collation_server")).scalar()
            db = conn.execute(text("SELECT DATABASE()")).scalar()

            def _column_collation(table: str, column: str) -> str | None:
                row = conn.execute(
                    text(
                        "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :t AND COLUMN_NAME = :c"
                    ),
                    {"db": db, "t": table, "c": column},
                ).fetchone()
                return row[0] if row else None

            reference = _column_collation("datasets", "id") or server_collation
            # 外键兼容基准：dataset_versions.(dataset_id|id|parent_version_id)
            # 必须与 datasets.id 一致，否则建外键会抛 MySQL 3780。
            for column in ("dataset_id", "id", "parent_version_id"):
                actual = _column_collation("dataset_versions", column)
                if actual is not None and actual != reference:
                    issues.append(
                        CollationIssue(table="dataset_versions", column=column, actual=actual, expected=reference)
                    )
    finally:
        engine.dispose()
    return CollationCheckResult(server_collation=server_collation, issues=issues)


def main() -> None:
    """命令行入口：HYDROLAB_DATABASE_URL 未配置时明确报错，不静默退化。"""
    import os
    import sys

    url = os.environ.get("HYDROLAB_DATABASE_URL")
    if not url:
        sys.stderr.write("HYDROLAB_DATABASE_URL 未配置；无法执行 collation 前置核查。\n")
        sys.exit(2)
    result = check_collation_consistency(url)
    print(f"server collation: {result.server_collation}")
    if result.ok:
        print("collation consistent: OK")
        sys.exit(0)
    for issue in result.issues:
        print(f"MISMATCH {issue.table}.{issue.column}: {issue.actual} != {issue.expected}")
    sys.exit(1)


if __name__ == "__main__":
    main()