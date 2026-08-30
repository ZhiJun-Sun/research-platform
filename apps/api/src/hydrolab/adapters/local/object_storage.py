"""本地文件系统版 ObjectStorage：无 S3 环境的开发/联调实现。"""

import hashlib
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from hydrolab.core.errors import conflict, not_found, validation_error
from hydrolab.ports.dto import (
    ObjectInfo,
    ObjectRef,
    UploadedPart,
    UploadRequest,
    UploadSession,
)


class LocalFilesystemObjectStorage:
    """语义与 Fake/S3 对齐；对象内容写入 root 下按 key 组织的路径。"""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._sessions: dict[str, UploadRequest] = {}

    def _path(self, key: str) -> Path:
        # 防路径穿越：归一化后必须仍位于 root 内
        candidate = (self._root / key).resolve()
        if self._root.resolve() not in candidate.parents and candidate != self._root.resolve():
            raise validation_error("非法对象 key", {"key": key})
        return candidate

    def put_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def create_upload(self, request: UploadRequest) -> UploadSession:
        if request.size_bytes < 0:
            raise validation_error("size_bytes 非法", {"size_bytes": request.size_bytes})
        if self._path(request.key).exists():
            raise conflict("对象已存在", {"key": request.key})
        session = UploadSession(
            session_id=uuid4().hex,
            key=request.key,
            upload_url=None,  # 本地实现走服务端中转写入
            part_size=8 * 1024**2 if request.multipart else None,
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        self._sessions[session.session_id] = request
        return session

    async def complete_upload(self, session_id: str, parts: list[UploadedPart]) -> ObjectInfo:
        request = self._sessions.pop(session_id, None)
        if request is None:
            raise not_found("上传会话不存在或已完成")
        path = self._path(request.key)
        if not path.exists():
            raise validation_error("对象内容缺失，无法完成上传", {"key": request.key})
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if request.sha256 and request.sha256 != actual:
            raise validation_error(
                "sha256 校验失败", {"declared": request.sha256, "actual": actual}
            )
        return ObjectInfo(
            key=request.key,
            size_bytes=len(data),
            sha256=actual,
            etag=actual[:32],
            content_type=request.content_type,
        )

    async def head(self, ref: ObjectRef) -> ObjectInfo:
        path = self._path(ref.key)
        if not path.exists():
            raise not_found("对象不存在")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        return ObjectInfo(key=ref.key, size_bytes=len(data), sha256=digest, etag=digest[:32])

    async def open_range(self, ref: ObjectRef, start: int, end: int | None = None) -> BinaryIO:
        path = self._path(ref.key)
        if not path.exists():
            raise not_found("对象不存在")
        if start < 0 or (end is not None and end < start):
            raise validation_error("非法 range", {"start": start, "end": end})
        data = path.read_bytes()
        return io.BytesIO(data[start : end + 1 if end is not None else None])

    async def copy(self, source: ObjectRef, target: ObjectRef) -> ObjectInfo:
        src = self._path(source.key)
        if not src.exists():
            raise not_found("源对象不存在")
        self.put_bytes(target.key, src.read_bytes())
        return await self.head(target)

    async def create_download_url(self, ref: ObjectRef, expires_in: int) -> str:
        await self.head(ref)
        return f"local://download/{ref.key}?expires_in={expires_in}"

    async def delete_quarantined(self, ref: ObjectRef) -> None:
        path = self._path(ref.key)
        if path.exists():
            path.unlink()

    async def healthcheck(self) -> bool:
        self._root.mkdir(parents=True, exist_ok=True)
        return self._root.is_dir()
