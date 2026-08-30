"""B1 API 请求/响应 Schema（OpenAPI 契约，前后端唯一交互格式）。"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from hydrolab.domain.enums import ResourceType, Role, UserStatus

# ---------- 通用 ----------


class UserView(BaseModel):
    id: UUID
    email: str
    display_name: str
    is_admin: bool
    status: UserStatus
    created_at: datetime


class TokenPairView(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResponse(BaseModel):
    user: UserView
    tokens: TokenPairView


# ---------- 认证 ----------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AcceptInvitationRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)


# ---------- 邀请 ----------


class CreateInvitationRequest(BaseModel):
    email: EmailStr
    expires_in_hours: int = Field(default=72, ge=1, le=24 * 30)


class InvitationView(BaseModel):
    id: UUID
    email: str
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class CreateInvitationResponse(BaseModel):
    invitation: InvitationView
    token: str  # 仅创建时返回一次


# ---------- 偏好 ----------


class PreferencesView(BaseModel):
    preferences: dict[str, Any]


class UpdatePreferencesRequest(BaseModel):
    preferences: dict[str, Any]


# ---------- 授权 ----------


class GrantView(BaseModel):
    id: UUID
    resource_type: ResourceType
    resource_id: UUID
    subject_id: UUID
    role: Role
    expires_at: datetime | None
    created_at: datetime


class CreateGrantRequest(BaseModel):
    email: EmailStr
    role: Role


# ---------- 分享 ----------


class CreateShareLinkRequest(BaseModel):
    resource_type: ResourceType
    resource_id: UUID
    resource_version_id: UUID | None = None
    allowed_artifact_kinds: list[str] = Field(default_factory=list)
    expires_in_hours: int = Field(default=24 * 7, ge=1, le=24 * 30)


class ShareLinkView(BaseModel):
    id: UUID
    resource_type: ResourceType
    resource_id: UUID
    resource_version_id: UUID | None
    allowed_artifact_kinds: list[str]
    expires_at: datetime
    revoked_at: datetime | None
    access_count: int
    last_accessed_at: datetime | None
    created_at: datetime


class CreateShareLinkResponse(BaseModel):
    share_link: ShareLinkView
    token: str | None  # 幂等命中时为 None
    url: str


class SharedResourceView(BaseModel):
    """公开访问的字段白名单视图：不含任何凭证、owner 内部信息。"""

    resource_type: ResourceType
    resource_id: UUID
    resource_version_id: UUID | None
    allowed_artifact_kinds: list[str]
    permissions: list[str] = ["read"]
    expires_at: datetime
