"""内存版 ObjectStorage：供单元测试与无外部服务环境使用。"""

import hashlib
import io
from datetime import UTC, datetime, timedelta
from typing import BinaryIO
from uuid import uuid4

from hydrolab.adapters.fake.base import FailureInjector
from hydrolab.core.errors import conflict, not_found, validation_error
from hydrolab.ports.dto import (
    ObjectInfo,
    ObjectRef,
    UploadedPart,
    UploadRequest,
    UploadSession,
)


class FakeObjectStorage:
    """两阶段上传语义与真实 S3 Adapter 对齐：先 create_upload，再 complete_upload。"""

    def __init__(self) -> None:
        self.injector = FailureInjector()
        self._objects: dict[str, bytes] = {}
        self._sessions: dict[str, UploadRequest] = {}
        self._deleted: list[str] = []

    # 测试辅助：模拟客户端已完成直传
    def put_bytes(self, key: str, data: bytes) -> None:
        self._objects[key] = data

    async def create_upload(self, request: UploadRequest) -> UploadSession:
        self.injector._record("create_upload", request)
        if request.size_bytes < 0:
            raise validation_error("size_bytes 非法", {"size_bytes": request.size_bytes})
        if request.key in self._objects:
            raise conflict("对象已存在", {"key": request.key})
        session = UploadSession(
            session_id=uuid4().hex,
            key=request.key,
            upload_url=f"fake://upload/{uuid4().hex}",
            part_size=8 * 1024**2 if request.multipart else None,
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        self._sessions[session.session_id] = request
        return session

    async def complete_upload(self, session_id: str, parts: list[UploadedPart]) -> ObjectInfo:
        self.injector._record("complete_upload", session_id, parts)
        request = self._sessions.pop(session_id, None)
        if request is None:
            raise not_found("上传会话不存在或已完成")
        data = self._objects.get(request.key)
        if data is None:
            raise validation_error("对象内容缺失，无法完成上传", {"key": request.key})
        declared = request.sha256
        actual = hashlib.sha256(data).hexdigest()
        if declared and declared != actual:
            raise validation_error(
                "sha256 校验失败", {"declared": declared, "actual": actual}
            )
        return ObjectInfo(
            key=request.key,
            size_bytes=len(data),
            sha256=actual,
            etag=actual[:32],
            content_type=request.content_type,
        )

    async def head(self, ref: ObjectRef) -> ObjectInfo:
        self.injector._record("head", ref)
        data = self._objects.get(ref.key)
        if data is None:
            raise not_found("对象不存在")
        digest = hashlib.sha256(data).hexdigest()
        return ObjectInfo(key=ref.key, size_bytes=len(data), sha256=digest, etag=digest[:32])

    async def open_range(self, ref: ObjectRef, start: int, end: int | None = None) -> BinaryIO:
        self.injector._record("open_range", ref, start, end)
        data = self._objects.get(ref.key)
        if data is None:
            raise not_found("对象不存在")
        if start < 0 or (end is not None and end < start):
            raise validation_error("非法 range", {"start": start, "end": end})
        return io.BytesIO(data[start : end + 1 if end is not None else None])

    async def copy(self, source: ObjectRef, target: ObjectRef) -> ObjectInfo:
        self.injector._record("copy", source, target)
        data = self._objects.get(source.key)
        if data is None:
            raise not_found("源对象不存在")
        self._objects[target.key] = data
        return await self.head(target)

    async def create_download_url(self, ref: ObjectRef, expires_in: int) -> str:
        self.injector._record("create_download_url", ref, expires_in)
        await self.head(ref)
        return f"fake://download/{ref.key}?expires_in={expires_in}"

    async def delete_quarantined(self, ref: ObjectRef) -> None:
        self.injector._record("delete_quarantined", ref)
        self._objects.pop(ref.key, None)
        self._deleted.append(ref.key)

    async def healthcheck(self) -> bool:
        self.injector._record("healthcheck")
        return True
