"""对象存储端口（plans/05 第 4 节）。

实现：FakeObjectStorage → LocalFilesystemObjectStorage → S3ObjectStorageAdapter。
"""

from typing import BinaryIO, Protocol

from hydrolab.ports.dto import (
    ObjectInfo,
    ObjectRef,
    UploadedPart,
    UploadRequest,
    UploadSession,
)


class ObjectStorage(Protocol):
    async def create_upload(self, request: UploadRequest) -> UploadSession: ...

    async def complete_upload(
        self, session_id: str, parts: list[UploadedPart]
    ) -> ObjectInfo: ...

    async def head(self, ref: ObjectRef) -> ObjectInfo: ...

    async def open_range(
        self, ref: ObjectRef, start: int, end: int | None = None
    ) -> BinaryIO: ...

    async def copy(self, source: ObjectRef, target: ObjectRef) -> ObjectInfo: ...

    async def create_download_url(self, ref: ObjectRef, expires_in: int) -> str: ...

    async def delete_quarantined(self, ref: ObjectRef) -> None: ...

    async def healthcheck(self) -> bool: ...
