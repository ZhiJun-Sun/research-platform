"""B3 代码导入应用服务；只解析归档，不执行归档内代码。"""

import hashlib
import io
from pathlib import PurePosixPath
from urllib.parse import urlparse
from uuid import UUID
from zipfile import ZipFile

from hydrolab.access.policy import AccessPolicy
from hydrolab.code_assets.entities import CodeRepository, CodeVersion
from hydrolab.code_assets.enums import CodeSourceType, CodeVersionStatus
from hydrolab.code_assets.repositories import CodeRepositoryStore, CodeVersionStore
from hydrolab.core.errors import AppError, not_found, validation_error
from hydrolab.domain.entities import ResourceGrant, User, utcnow
from hydrolab.domain.enums import ResourceType, Role
from hydrolab.ports import ObjectStorage
from hydrolab.repositories import GrantRepository

_MAX_FILES = 2_000
_MAX_FILE_BYTES = 20 * 1024 * 1024
_MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 100
_ALLOWED_MANIFESTS = {"requirements.txt", "pyproject.toml", "environment.yml", "Dockerfile", "hydro-experiment.yaml"}


class CodeImportService:
    def __init__(
        self,
        repos: CodeRepositoryStore,
        versions: CodeVersionStore,
        grants: GrantRepository,
        storage: ObjectStorage,
        policy: AccessPolicy,
    ) -> None:
        self._repos, self._versions, self._grants = repos, versions, grants
        self._storage, self._policy = storage, policy

    async def create_repository(self, owner: User, name: str, description: str = "") -> CodeRepository:
        if not name.strip():
            raise validation_error("代码仓库名称不能为空")
        repo = await self._repos.add(CodeRepository(owner_id=owner.id, name=name.strip(), description=description))
        await self._grants.add(
            ResourceGrant(
                resource_type=ResourceType.CODE_REPOSITORY,
                resource_id=repo.id,
                subject_id=owner.id,
                role=Role.OWNER,
                granted_by=owner.id,
            )
        )
        return repo

    async def import_zip(self, owner: User, repo_id: UUID, filename: str, archive: bytes) -> CodeVersion:
        await self._require_owner(owner, repo_id)
        if not filename.lower().endswith(".zip"):
            raise validation_error("代码导入仅接受 ZIP 归档")
        manifest = self._inspect_zip(archive)
        key = f"code-imports/{repo_id}/{hashlib.sha256(archive).hexdigest()}.zip"
        self._storage.put_bytes(key, archive)  # type: ignore[attr-defined]
        version = CodeVersion(
            repository_id=repo_id,
            version_no=await self._versions.next_version_no(repo_id),
            source_type=CodeSourceType.ZIP,
            status=CodeVersionStatus.READY,
            object_key=key,
            content_hash=hashlib.sha256(archive).hexdigest(),
            manifest=manifest,
            frozen_at=utcnow(),
        )
        return await self._versions.add(version)

    async def register_git(
        self, owner: User, repo_id: UUID, source_ref: str, commit_sha: str | None = None
    ) -> CodeVersion:
        await self._require_owner(owner, repo_id)
        parsed = urlparse(source_ref)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise validation_error("Git 地址必须是无凭证的 HTTPS URL")
        version = CodeVersion(
            repository_id=repo_id,
            version_no=await self._versions.next_version_no(repo_id),
            source_type=CodeSourceType.GIT,
            status=CodeVersionStatus.PENDING,
            source_ref=source_ref,
            commit_sha=commit_sha,
        )
        return await self._versions.add(version)

    async def get_repository(self, actor: User, repo_id: UUID) -> CodeRepository:
        repo = await self._repos.get(repo_id)
        if repo is None:
            raise not_found("代码仓库不存在")
        await self._policy.require(actor, ResourceType.CODE_REPOSITORY, repo_id, Role.VIEWER)
        return repo

    async def _require_owner(self, actor: User, repo_id: UUID) -> None:
        await self._policy.require(actor, ResourceType.CODE_REPOSITORY, repo_id, Role.OWNER)

    @staticmethod
    def _inspect_zip(archive: bytes) -> dict[str, object]:
        try:
            with ZipFile(io.BytesIO(archive)) as zip_file:
                infos = zip_file.infolist()
                if len(infos) > _MAX_FILES:
                    raise validation_error("ZIP 文件数量超过安全上限")
                total = 0
                paths: list[str] = []
                manifests: list[str] = []
                for info in infos:
                    path = PurePosixPath(info.filename)
                    if path.is_absolute() or ".." in path.parts or not info.filename:
                        raise validation_error("ZIP 包含非法路径")
                    if info.is_dir():
                        continue
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise validation_error("ZIP 不允许符号链接")
                    if info.file_size > _MAX_FILE_BYTES:
                        raise validation_error("ZIP 内单文件超过安全上限")
                    if info.compress_size and info.file_size / info.compress_size > _MAX_COMPRESSION_RATIO:
                        raise validation_error("ZIP 压缩比异常，疑似压缩炸弹")
                    total += info.file_size
                    if total > _MAX_UNCOMPRESSED_BYTES:
                        raise validation_error("ZIP 解压后总大小超过安全上限")
                    paths.append(info.filename)
                    if path.name in _ALLOWED_MANIFESTS:
                        manifests.append(info.filename)
                return {
                    "file_count": len(paths),
                    "uncompressed_bytes": total,
                    "files": paths[:100],
                    "detected_manifests": sorted(manifests),
                }
        except AppError:
            raise
        except Exception as exc:
            raise validation_error("无法读取 ZIP 归档") from exc
