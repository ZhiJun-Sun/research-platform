"""ObjectStorage 端口契约测试。

同一组测试必须对 Fake、Local 以及未来的 S3ObjectStorageAdapter 全部通过
（plans/05 第 3、15 节：共享 contract tests）。
"""

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest

from hydrolab.adapters.fake import FakeObjectStorage
from hydrolab.adapters.local import LocalFilesystemObjectStorage
from hydrolab.core.errors import AppError
from hydrolab.ports import ObjectStorage
from hydrolab.ports.dto import ObjectRef, UploadedPart, UploadRequest

CONTENT = b"hydrolab-contract-test-payload" * 100


def _storage_factories(tmp_path: Path) -> dict[str, ObjectStorage]:
    return {
        "fake": FakeObjectStorage(),
        "local": LocalFilesystemObjectStorage(tmp_path / "objects"),
    }


@pytest.fixture(params=["fake", "local"])
async def storage(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[ObjectStorage]:
    yield _storage_factories(tmp_path)[request.param]


def _put_for(storage: ObjectStorage, key: str, data: bytes) -> None:
    # 两种当前实现都提供 put_bytes 测试辅助；S3 实现接入时改为预签名直传模拟
    storage.put_bytes(key, data)  # type: ignore[attr-defined]


async def _full_upload(storage: ObjectStorage, key: str, data: bytes = CONTENT) -> None:
    session = await storage.create_upload(
        UploadRequest(
            key=key,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            multipart=True,
        )
    )
    _put_for(storage, key, data)
    await storage.complete_upload(
        session.session_id, [UploadedPart(part_number=1, etag="e1", size_bytes=len(data))]
    )


async def test_two_phase_upload_and_head(storage: ObjectStorage) -> None:
    key = f"artifacts/{uuid4().hex}/data.bin"
    await _full_upload(storage, key)
    info = await storage.head(ObjectRef(key=key))
    assert info.size_bytes == len(CONTENT)
    assert info.sha256 == hashlib.sha256(CONTENT).hexdigest()


async def test_upload_rejects_sha256_mismatch(storage: ObjectStorage) -> None:
    key = f"artifacts/{uuid4().hex}/bad.bin"
    session = await storage.create_upload(
        UploadRequest(key=key, size_bytes=len(CONTENT), sha256="0" * 64)
    )
    _put_for(storage, key, CONTENT)
    with pytest.raises(AppError) as exc:
        await storage.complete_upload(
            session.session_id,
            [UploadedPart(part_number=1, etag="e1", size_bytes=len(CONTENT))],
        )
    assert exc.value.code == "VALIDATION_ERROR"


async def test_complete_unknown_session_fails(storage: ObjectStorage) -> None:
    with pytest.raises(AppError) as exc:
        await storage.complete_upload("no-such-session", [])
    assert exc.value.code == "NOT_FOUND"


async def test_duplicate_key_upload_conflicts(storage: ObjectStorage) -> None:
    key = f"artifacts/{uuid4().hex}/dup.bin"
    await _full_upload(storage, key)
    with pytest.raises(AppError) as exc:
        await storage.create_upload(UploadRequest(key=key, size_bytes=1))
    assert exc.value.code == "CONFLICT"


async def test_open_range_roundtrip(storage: ObjectStorage) -> None:
    key = f"logs/{uuid4().hex}/run.log"
    await _full_upload(storage, key)
    reader = await storage.open_range(ObjectRef(key=key), start=10, end=29)
    assert reader.read() == CONTENT[10:30]


async def test_copy_preserves_content(storage: ObjectStorage) -> None:
    src = f"artifacts/{uuid4().hex}/src.bin"
    dst = f"artifacts/{uuid4().hex}/dst.bin"
    await _full_upload(storage, src)
    info = await storage.copy(ObjectRef(key=src), ObjectRef(key=dst))
    assert info.sha256 == hashlib.sha256(CONTENT).hexdigest()


async def test_download_url_requires_existing_object(storage: ObjectStorage) -> None:
    with pytest.raises(AppError) as exc:
        await storage.create_download_url(ObjectRef(key="missing.bin"), 60)
    assert exc.value.code == "NOT_FOUND"


async def test_delete_quarantined(storage: ObjectStorage) -> None:
    key = f"quarantine/{uuid4().hex}/x.bin"
    await _full_upload(storage, key)
    await storage.delete_quarantined(ObjectRef(key=key))
    with pytest.raises(AppError):
        await storage.head(ObjectRef(key=key))


async def test_healthcheck(storage: ObjectStorage) -> None:
    assert await storage.healthcheck() is True


async def test_local_rejects_path_traversal(tmp_path: Path) -> None:
    storage = LocalFilesystemObjectStorage(tmp_path / "objects")
    with pytest.raises(AppError) as exc:
        await storage.create_upload(UploadRequest(key="../escape.bin", size_bytes=1))
    assert exc.value.code == "VALIDATION_ERROR"
