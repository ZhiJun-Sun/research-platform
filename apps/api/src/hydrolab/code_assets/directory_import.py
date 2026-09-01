"""本地目录快照导入（e2e：把服务器上的一个真实工程目录固化为不可变 CodeVersion）。

设计约束（与 plans/05 Adapter 准入一致）：
- 只读取目录内容，绝不执行目录内代码；
- 导入范围受 allowlist 根目录约束，防止把任意主机路径打包外泄；
- 忽略规则默认排除虚拟环境、缓存、大数据与既有实验产物，避免把几十 GB 数据混入代码包；
- 产物是确定性 ZIP（固定时间戳、排序路径），因此同一目录内容 → 同一 content_hash；
- manifest 记录文件清单与逐文件 sha256，供后续复现与审计。
"""

from __future__ import annotations

import hashlib
import io
import os
import zipfile
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from uuid import UUID

from hydrolab.access.policy import AccessPolicy
from hydrolab.code_assets.entities import CodeVersion
from hydrolab.code_assets.enums import CodeSourceType, CodeVersionStatus
from hydrolab.code_assets.repositories import CodeVersionStore
from hydrolab.core.errors import validation_error
from hydrolab.domain.entities import utcnow
from hydrolab.domain.enums import ResourceType, Role
from hydrolab.domain.entities import User
from hydrolab.ports import ObjectStorage

# 确定性 ZIP 时间戳（1980-01-01，ZIP 纪元下界），保证同内容同 hash
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
    # 版本控制与 IDE
    ".git",
    ".git/*",
    ".svn",
    ".hg",
    ".idea",
    ".idea/*",
    ".vscode",
    ".vscode/*",
    ".DS_Store",
    "**/.DS_Store",
    # Python 缓存与虚拟环境
    "__pycache__",
    "**/__pycache__",
    "**/__pycache__/*",
    "*.pyc",
    "**/*.pyc",
    ".venv*",
    ".venv*/*",
    "venv",
    "venv/*",
    "env",
    "env/*",
    ".mypy_cache",
    ".mypy_cache/*",
    ".pytest_cache",
    ".pytest_cache/*",
    ".ruff_cache",
    ".ruff_cache/*",
    # 平台自身与工具目录
    ".codeflicker",
    ".codeflicker/*",
    # 大数据与既有产物：代码包只装代码，数据/结果走 DatasetVersion 与 Artifact
    "datasets",
    "datasets/*",
    "experiments",
    "experiments/*",
    "logs",
    "logs/*",
    "result",
    "result/*",
    "metric_record",
    "metric_record/*",
    "backup",
    "backup/*",
    "temp",
    "temp/*",
    "pids",
    "pids/*",
    # 权重与二进制产物
    "*.pth",
    "**/*.pth",
    "*.ckpt",
    "**/*.ckpt",
    "*.xlsx",
    "**/*.xlsx",
    "*.csv",
    "**/*.csv",
)

_MAX_FILES = 5_000
_MAX_FILE_BYTES = 20 * 1024 * 1024
_MAX_TOTAL_BYTES = 200 * 1024 * 1024
_MANIFEST_NAMES = {
    "requirements.txt",
    "pyproject.toml",
    "environment.yml",
    "Dockerfile",
    "hydro-experiment.yaml",
}


@dataclass
class DirectorySnapshot:
    """目录快照结果。archive 为确定性 ZIP 字节。"""

    archive: bytes
    content_hash: str
    files: list[str] = field(default_factory=list)
    file_hashes: dict[str, str] = field(default_factory=dict)
    total_bytes: int = 0
    skipped: list[str] = field(default_factory=list)
    detected_manifests: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)


def _matches(rel_posix: str, name: str, patterns: tuple[str, ...] | list[str]) -> bool:
    for pattern in patterns:
        if fnmatch(rel_posix, pattern) or fnmatch(name, pattern):
            return True
        # 目录前缀匹配：pattern "datasets" 应覆盖 "datasets/a/b.txt"
        if rel_posix == pattern or rel_posix.startswith(pattern.rstrip("/*") + "/"):
            if pattern.rstrip("/*"):
                return True
    return False


def snapshot_directory(
    source: Path,
    extra_ignore: list[str] | None = None,
    include_patterns: list[str] | None = None,
) -> DirectorySnapshot:
    """把目录打包为确定性 ZIP，并计算清单与哈希。不执行任何目录内代码。"""

    root = source.resolve()
    if not root.is_dir():
        raise validation_error("导入路径不是目录", {"path": str(source)})

    patterns = list(DEFAULT_IGNORE_PATTERNS) + list(extra_ignore or [])
    # 支持 .hydrolabignore：每行一个 glob，# 开头为注释
    ignore_file = root / ".hydrolabignore"
    if ignore_file.is_file():
        for line in ignore_file.read_text(encoding="utf-8", errors="replace").splitlines():
            entry = line.strip()
            if entry and not entry.startswith("#"):
                patterns.append(entry)

    collected: list[tuple[str, Path]] = []
    skipped: list[str] = []
    total = 0

    for current_dir, dir_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_dir)
        rel_dir = current.relative_to(root).as_posix()
        # 原地裁剪目录遍历，避免进入 .venv / datasets 等大目录
        kept_dirs = []
        for name in sorted(dir_names):
            rel = name if rel_dir in ("", ".") else f"{rel_dir}/{name}"
            child = current / name
            if child.is_symlink():
                skipped.append(f"{rel} (symlink)")
                continue
            if _matches(rel, name, patterns):
                skipped.append(f"{rel}/ (ignored)")
                continue
            kept_dirs.append(name)
        dir_names[:] = kept_dirs

        for name in sorted(file_names):
            rel = name if rel_dir in ("", ".") else f"{rel_dir}/{name}"
            path = current / name
            if path.is_symlink():
                skipped.append(f"{rel} (symlink)")
                continue
            if not path.is_file():
                continue
            if include_patterns and not _matches(rel, name, include_patterns):
                continue
            if _matches(rel, name, patterns):
                skipped.append(f"{rel} (ignored)")
                continue
            size = path.stat().st_size
            if size > _MAX_FILE_BYTES:
                skipped.append(f"{rel} (too large: {size} bytes)")
                continue
            total += size
            if total > _MAX_TOTAL_BYTES:
                raise validation_error(
                    "目录快照超过大小上限，请通过忽略规则排除数据目录",
                    {"limit_bytes": _MAX_TOTAL_BYTES},
                )
            collected.append((rel, path))
            if len(collected) > _MAX_FILES:
                raise validation_error("目录文件数量超过安全上限", {"limit": _MAX_FILES})

    if not collected:
        raise validation_error("目录内没有可导入的代码文件（可能全部被忽略规则排除）")

    collected.sort(key=lambda item: item[0])
    file_hashes: dict[str, str] = {}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel, path in collected:
            data = path.read_bytes()
            file_hashes[rel] = hashlib.sha256(data).hexdigest()
            info = zipfile.ZipInfo(filename=rel, date_time=_ZIP_EPOCH)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)

    payload = buffer.getvalue()
    # content_hash 基于内容清单而非 ZIP 字节，避免压缩实现差异影响可复现性
    digest_source = "\n".join(f"{rel}:{file_hashes[rel]}" for rel, _ in collected)
    content_hash = hashlib.sha256(digest_source.encode()).hexdigest()

    files = [rel for rel, _ in collected]
    manifests = sorted(rel for rel in files if Path(rel).name in _MANIFEST_NAMES)
    entrypoints = sorted(rel for rel in files if "/" not in rel and rel.endswith(".py"))

    return DirectorySnapshot(
        archive=payload,
        content_hash=content_hash,
        files=files,
        file_hashes=file_hashes,
        total_bytes=total,
        skipped=skipped[:200],
        detected_manifests=manifests,
        entrypoints=entrypoints,
    )


class DirectoryImportService:
    """把受控主机目录导入为不可变 CodeVersion。"""

    def __init__(
        self,
        versions: CodeVersionStore,
        storage: ObjectStorage,
        policy: AccessPolicy,
        allowed_roots: list[Path],
    ) -> None:
        self._versions = versions
        self._storage = storage
        self._policy = policy
        self._allowed_roots = [Path(root).expanduser().resolve() for root in allowed_roots]

    @property
    def allowed_roots(self) -> list[str]:
        return [str(root) for root in self._allowed_roots]

    def _resolve_allowed(self, raw_path: str) -> Path:
        if not raw_path.strip():
            raise validation_error("导入目录不能为空")
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            raise validation_error("导入目录必须是绝对路径", {"path": raw_path})
        resolved = candidate.resolve()
        if not self._allowed_roots:
            raise validation_error(
                "未配置允许导入的根目录，请设置 HYDROLAB_CODE_IMPORT_ROOTS",
            )
        for root in self._allowed_roots:
            if resolved == root or root in resolved.parents:
                return resolved
        raise validation_error(
            "导入目录不在允许的根目录内",
            {"path": str(resolved), "allowed_roots": self.allowed_roots},
        )

    def preview(
        self, path: str, extra_ignore: list[str] | None = None
    ) -> tuple[Path, DirectorySnapshot]:
        resolved = self._resolve_allowed(path)
        return resolved, snapshot_directory(resolved, extra_ignore)

    async def import_directory(
        self,
        owner: User,
        repo_id: UUID,
        path: str,
        extra_ignore: list[str] | None = None,
    ) -> tuple[CodeVersion, DirectorySnapshot]:
        await self._policy.require(owner, ResourceType.CODE_REPOSITORY, repo_id, Role.OWNER)
        resolved, snapshot = self.preview(path, extra_ignore)
        key = f"code-imports/{repo_id}/dir-{snapshot.content_hash}.zip"
        self._storage.put_bytes(key, snapshot.archive)  # type: ignore[attr-defined]
        version = CodeVersion(
            repository_id=repo_id,
            version_no=await self._versions.next_version_no(repo_id),
            source_type=CodeSourceType.ZIP,
            status=CodeVersionStatus.READY,
            object_key=key,
            source_ref=f"dir://{resolved}",
            content_hash=snapshot.content_hash,
            manifest={
                "import_kind": "directory_snapshot",
                "source_path": str(resolved),
                "file_count": len(snapshot.files),
                "uncompressed_bytes": snapshot.total_bytes,
                "archive_bytes": len(snapshot.archive),
                "files": snapshot.files[:200],
                "file_hashes": snapshot.file_hashes,
                "detected_manifests": snapshot.detected_manifests,
                "entrypoints": snapshot.entrypoints,
                "skipped_sample": snapshot.skipped[:50],
            },
            frozen_at=utcnow(),
        )
        return await self._versions.add(version), snapshot
