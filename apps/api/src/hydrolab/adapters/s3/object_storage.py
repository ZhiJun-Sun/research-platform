"""S3-compatible ObjectStorage 真实实现（S3-01 Spike 适配器）。

使用 aiobotocore 异步 S3 客户端，对齐 Fake/Local 的两阶段上传语义：
- create_upload：单对象返回预签名 PUT URL；multipart 创建分片会话并返回
  预签名首分片 URL 与分片大小。
- complete_upload：单对象经 HEAD 校验对象已直传；multipart 用回传 parts 完成合并且校验。
契约：与对象存储契约测试共用同一组断言（plans/05 §4.4 S3-01）。

注意：aiobotocore 的客户端方法本身是协程，必须直接 await，不能 asyncio.to_thread。

安全约束（plans/05 §4.3）：
- 业务真相源仍在 PostgreSQL；这里只做对象读写；
- 下载一律用过时预签名 URL，不暴露永久对象地址；
- 凭证只进入 aiobotocore 配置，绝不写入日志或异常消息。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import BinaryIO
from uuid import uuid4

from hydrolab.core.errors import not_found, validation_error
from hydrolab.ports.dto import (
    ObjectInfo,
    ObjectRef,
    UploadedPart,
    UploadRequest,
    UploadSession,
)

_CONTENT_TYPE = "application/octet-stream"


@dataclass
class _Session:
    request: UploadRequest
    upload_id: str | None  # multipart 会话 id；单对象为 None
    bucket: str


class S3ObjectStorageAdapter:
    """S3/MinIO 对象存储适配器。语义与 FakeObjectStorage / LocalFilesystem 一致。"""

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
        addressing_style: str = "path",
        session_ttl_seconds: int = 1800,
    ) -> None:
        self._endpoint = endpoint
        self._bucket = bucket
        self._access_key = access_key or ""
        self._secret_key = secret_key or ""
        self._region = region
        self._addressing_style = addressing_style
        self._session_ttl = session_ttl_seconds
        self._sessions: dict[str, _Session] = {}

    def _client(self):
        from aiobotocore.session import get_session
        from botocore.config import Config

        session = get_session()
        return session.create_client(
            "s3",
            region_name=self._region,
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key or None,
            aws_secret_access_key=self._secret_key or None,
            config=Config(s3={"addressing_style": self._addressing_style}),
        )

    def put_bytes(self, key: str, data: bytes) -> None:
        """Synchronous collector hook; collector runs in a worker thread."""
        import boto3
        from botocore.config import Config

        self._validate_key(key)
        client = boto3.client(
            "s3", endpoint_url=self._endpoint, region_name=self._region,
            aws_access_key_id=self._access_key or None,
            aws_secret_access_key=self._secret_key or None,
            config=Config(s3={"addressing_style": self._addressing_style}),
        )
        try:
            client.put_object(Bucket=self._bucket, Key=key, Body=data)
        finally:
            client.close()

    @staticmethod
    def _validate_key(key: str) -> None:
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise validation_error("非法对象 key", {"key": key})

    # ---------- 两阶段上传 ----------
    async def create_upload(self, request: UploadRequest) -> UploadSession:
        if request.size_bytes < 0:
            raise validation_error("size_bytes 非法", {"size_bytes": request.size_bytes})
        self._validate_key(request.key)
        session_id = uuid4().hex
        upload_id: str | None = None
        upload_url: str | None = None
        part_size: int | None = None

        try:
            async with self._client() as s3:
                if request.multipart:
                    resp = await s3.create_multipart_upload(
                        Bucket=self._bucket,
                        Key=request.key,
                        ContentType=request.content_type,
                    )
                    upload_id = resp["UploadId"]
                    upload_url = await s3.generate_presigned_url(
                        "upload_part",
                        Params={
                            "Bucket": self._bucket,
                            "Key": request.key,
                            "UploadId": upload_id,
                            "PartNumber": 1,
                        },
                        ExpiresIn=self._session_ttl,
                    )
                    part_size = 8 * 1024**2
                else:
                    upload_url = await s3.generate_presigned_url(
                        "put_object",
                        Params={
                            "Bucket": self._bucket,
                            "Key": request.key,
                            "ContentType": request.content_type,
                        },
                        ExpiresIn=self._session_ttl,
                    )
        except Exception as exc:
            raise validation_error(
                "创建上传会话失败", {"reason": exc.__class__.__name__}
            ) from exc

        self._sessions[session_id] = _Session(request=request, upload_id=upload_id, bucket=self._bucket)
        return UploadSession(
            session_id=session_id,
            key=request.key,
            upload_url=upload_url,
            part_size=part_size,
            expires_at=datetime.now(UTC) + timedelta(seconds=self._session_ttl),
        )

    async def complete_upload(self, session_id: str, parts: list[UploadedPart]) -> ObjectInfo:
        session = self._sessions.pop(session_id, None)
        if session is None:
            raise not_found("上传会话不存在或已完成")
        request = session.request
        self._validate_key(request.key)

        try:
            async with self._client() as s3:
                if session.upload_id is not None:
                    # multipart：用客户端回传的分片 etag 完成合并
                    multipart = {
                        "Parts": [
                            {
                                "PartNumber": p.part_number,
                                "ETag": p.etag,
                            }
                            for p in sorted(parts, key=lambda x: x.part_number)
                        ]
                    }
                    await s3.complete_multipart_upload(
                        Bucket=session.bucket,
                        Key=request.key,
                        MultipartUpload=multipart,
                        UploadId=session.upload_id,
                    )
                # 单对象：客户端已通过预签名 PUT 直传，这里 HEAD 确认即可
                info = await self.head(ObjectRef(key=request.key))
        except Exception as exc:
            raise validation_error("上传未完成", {"reason": exc.__class__.__name__}) from exc
        return info

    # ---------- 读取 ----------
    async def head(self, ref: ObjectRef) -> ObjectInfo:
        self._validate_key(ref.key)
        try:
            async with self._client() as s3:
                resp = await s3.head_object(Bucket=self._bucket, Key=ref.key)
                size = int(resp.get("ContentLength", 0))
                etag = str(resp.get("ETag", "")).strip('"')
                content_type = resp.get("ContentType", _CONTENT_TYPE)
        except Exception as exc:
            raise not_found("对象不存在") from exc
        return ObjectInfo(
            key=ref.key, size_bytes=size, sha256=None, etag=etag or None, content_type=content_type
        )

    async def open_range(self, ref: ObjectRef, start: int, end: int | None = None) -> BinaryIO:
        import io

        self._validate_key(ref.key)
        if start < 0 or (end is not None and end < start):
            raise validation_error("非法 range", {"start": start, "end": end})
        range_header = f"bytes={start}-{end if end is not None else ''}"
        try:
            async with self._client() as s3:
                resp = await s3.get_object(Bucket=self._bucket, Key=ref.key, Range=range_header)
                body = await resp["Body"].read()
        except Exception as exc:
            raise not_found("对象不存在") from exc
        return io.BytesIO(body)

    async def copy(self, source: ObjectRef, target: ObjectRef) -> ObjectInfo:
        self._validate_key(source.key)
        self._validate_key(target.key)
        try:
            async with self._client() as s3:
                await s3.copy_object(
                    Bucket=self._bucket,
                    Key=target.key,
                    CopySource={"Bucket": self._bucket, "Key": source.key},
                )
        except Exception as exc:
            raise not_found("源对象不存在") from exc
        return await self.head(target)

    async def create_download_url(self, ref: ObjectRef, expires_in: int) -> str:
        self._validate_key(ref.key)
        try:
            async with self._client() as s3:
                url = await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": ref.key},
                    ExpiresIn=expires_in,
                )
        except Exception as exc:
            raise not_found("对象不存在") from exc
        return url

    async def delete_quarantined(self, ref: ObjectRef) -> None:
        self._validate_key(ref.key)
        try:
            async with self._client() as s3:
                await s3.delete_object(Bucket=self._bucket, Key=ref.key)
        except Exception:
            pass

    async def healthcheck(self) -> bool:
        try:
            async with self._client() as s3:
                await s3.list_objects_v2(Bucket=self._bucket, MaxKeys=1)
            return True
        except Exception:
            return False
