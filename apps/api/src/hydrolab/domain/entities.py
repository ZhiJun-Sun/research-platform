"""领域实体。

规则（plans/02 第 3、4 节）：
- 主键 UUID；时间均为 UTC；
- 密码/Token 只保存安全哈希，原始值仅在创建时返回一次；
- 分享链接锁定资源版本，支持过期与撤销。
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from hydrolab.domain.enums import ResourceType, Role, SubjectType, UserStatus


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    email: str
    display_name: str
    password_hash: str
    status: UserStatus = UserStatus.ACTIVE
    is_admin: bool = False
    preferences: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class Invitation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    token_hash: str
    email: str
    inviter_id: UUID
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)

    def is_usable(self, now: datetime) -> bool:
        return self.accepted_at is None and self.revoked_at is None and self.expires_at > now


class Session(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    token_hash: str
    refresh_token_hash: str
    expires_at: datetime
    refresh_expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ResourceGrant(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    resource_type: ResourceType
    resource_id: UUID
    subject_type: SubjectType = SubjectType.USER
    subject_id: UUID
    role: Role
    granted_by: UUID
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ShareLink(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    token_hash: str
    resource_type: ResourceType
    resource_id: UUID
    resource_version_id: UUID | None = None  # 锁定版本；None 表示当前版本
    allowed_artifact_kinds: list[str] = Field(default_factory=list)
    created_by: UUID
    expires_at: datetime
    revoked_at: datetime | None = None
    access_count: int = 0
    last_accessed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)

    def is_usable(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now


class AuditLog(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    actor_id: UUID | None  # None 表示系统/匿名动作
    action: str
    resource_type: str | None = None
    resource_id: UUID | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
