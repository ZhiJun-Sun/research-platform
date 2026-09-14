"""S3ObjectStorageAdapter 单测。

本地环境无 Docker daemon，moto 5.2.3 与 aiobotocore 2.26 存在运行时版本不兼容，
故用可控的 fake S3 client 验证适配器的编排逻辑与错误映射（与 MLflow/Docker 单测同策略）。
真实 MinIO 冒烟（连接远程 9000）留到部署时用同一组契约断言执行（S3-01）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from hydrolab.adapters.s3 import S3ObjectStorageAdapter
from hydrolab.core.errors import AppError
from hydrolab.ports.dto import ObjectRef, UploadedPart, UploadRequest

CONTENT = b"s3-contract-payload-abc123"


class FakeS3Client:
    """最小可控 S3 client，提供适配器所需的协程方法。"""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    async def head_object(self, **kwargs):
        key = kwargs["Key"]
        if key not in self.store:
            raise AppError("404", "NoSuchKey")
        body = self.store[key]
        return {"ContentLength": len(body), "ETag": f'"{key}-etag"', "ContentType": "application/octet-stream"}

    async def put_object(self, **kwargs):
        self.store[kwargs["Key"]] = kwargs.get("Body", b"")

    async def get_object(self, **kwargs):
        key = kwargs["Key"]
        body = self.store.get(key)
        if body is None:
            raise AppError("404", "NoSuchKey")
        rng = kwargs.get("Range")
        if rng:
            _, spec = rng.split("=")
            start_s, _, end_s = spec.partition("-")
            start = int(start_s)
            end = int(end_s) if end_s else len(body) - 1
            body = body[start : end + 1]
        return {"Body": AsyncMock(read=AsyncMock(return_value=body)), "ContentLength": len(body)}

    async def copy_object(self, **kwargs):
        src = kwargs["CopySource"]["Key"]
        if src not in self.store:
            raise AppError("404", "NoSuchKey")
        self.store[kwargs["Key"]] = self.store[src]

    async def delete_object(self, **kwargs):
        self.store.pop(kwargs["Key"], None)

    async def generate_presigned_url(self, op, Params=None, ExpiresIn=0, **kwargs):
        return f"https://presigned.example/{op}?ExpiresIn={ExpiresIn}"

    async def list_objects_v2(self, **kwargs):
        return {"KeyCount": len(self.store)}

    async def create_multipart_upload(self, **kwargs):
        return {"UploadId": "upload-1"}

    async def complete_multipart_upload(self, **kwargs):
        return {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture()
def s3() -> S3ObjectStorageAdapter:
    adapter = S3ObjectStorageAdapter(
        endpoint="http://minio:9000",
        bucket="hydrolab",
        access_key="test",
        secret_key="test",
    )
    shared = FakeS3Client()
    # 复用同一 client 实例，保持 state 共享（真实 aiobotocore 连同一 S3）
    adapter._client = lambda: shared  # type: ignore[method-assign]
    return adapter


async def _upload(s3: S3ObjectStorageAdapter, key: str) -> None:
    session = await s3.create_upload(
        UploadRequest(key=key, size_bytes=len(CONTENT), multipart=False)
    )
    async with s3._client() as client:  # type: ignore[attr-defined]
        await client.put_object(Bucket="hydrolab", Key=key, Body=CONTENT)
    await s3.complete_upload(
        session.session_id, [UploadedPart(part_number=1, etag="e1", size_bytes=len(CONTENT))]
    )


async def test_two_phase_upload_and_head(s3: S3ObjectStorageAdapter) -> None:
    key = "artifacts/a/data.bin"
    await _upload(s3, key)
    info = await s3.head(ObjectRef(key=key))
    assert info.size_bytes == len(CONTENT)
    assert info.etag


async def test_create_upload_returns_presigned_url(s3: S3ObjectStorageAdapter) -> None:
    session = await s3.create_upload(
        UploadRequest(key="x.csv", size_bytes=100, multipart=True)
    )
    assert session.upload_url.startswith("https://presigned.example")
    assert session.part_size


async def test_missing_object_raises_not_found(s3: S3ObjectStorageAdapter) -> None:
    with pytest.raises(AppError):
        await s3.head(ObjectRef(key="no/such/key"))


async def test_range_read(s3: S3ObjectStorageAdapter) -> None:
    key = "artifacts/r.bin"
    await _upload(s3, key)
    data = (await s3.open_range(ObjectRef(key=key), start=0, end=5)).read()
    assert data == CONTENT[:6]


async def test_presigned_download_url(s3: S3ObjectStorageAdapter) -> None:
    key = "artifacts/d.bin"
    await _upload(s3, key)
    url = await s3.create_download_url(ObjectRef(key=key), expires_in=300)
    assert "presigned.example" in url and "300" in url


async def test_copy_object(s3: S3ObjectStorageAdapter) -> None:
    src, dst = "a.bin", "b.bin"
    await _upload(s3, src)
    info = await s3.copy(ObjectRef(key=src), ObjectRef(key=dst))
    assert info.size_bytes == len(CONTENT)
    assert (await s3.open_range(ObjectRef(key=dst), 0)).read() == CONTENT


async def test_healthcheck_ok(s3: S3ObjectStorageAdapter) -> None:
    assert await s3.healthcheck() is True


async def test_illegal_key_rejected(s3: S3ObjectStorageAdapter) -> None:
    with pytest.raises(AppError):
        await s3.head(ObjectRef(key="../escape"))


async def test_delete_quarantined(s3: S3ObjectStorageAdapter) -> None:
    key = "quarantine/bad.bin"
    await _upload(s3, key)
    await s3.delete_quarantined(ObjectRef(key=key))
    with pytest.raises(AppError):
        await s3.head(ObjectRef(key=key))