"""身份、授权领域 ORM 模型（B1：users/invitations/sessions/grants/share_links/audit_logs）。"""

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from hydrolab.db.base import Base, UTCDateTime, json_column, uuid_column


class UserModel(Base):
    __tablename__ = "users"

    id = mapped_column(uuid_column(), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    preferences = mapped_column(json_column())
    created_at = mapped_column(UTCDateTime())


class InvitationModel(Base):
    __tablename__ = "invitations"

    id = mapped_column(uuid_column(), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320))
    inviter_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    expires_at = mapped_column(UTCDateTime())
    accepted_at = mapped_column(UTCDateTime(), nullable=True)
    revoked_at = mapped_column(UTCDateTime(), nullable=True)
    created_at = mapped_column(UTCDateTime())


class SessionModel(Base):
    __tablename__ = "sessions"

    id = mapped_column(uuid_column(), primary_key=True)
    user_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(200), index=True)
    expires_at = mapped_column(UTCDateTime())
    refresh_expires_at = mapped_column(UTCDateTime())
    revoked_at = mapped_column(UTCDateTime(), nullable=True)
    created_at = mapped_column(UTCDateTime())


class GrantModel(Base):
    __tablename__ = "resource_grants"

    id = mapped_column(uuid_column(), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(40))
    resource_id = mapped_column(uuid_column(), index=True)
    subject_type: Mapped[str] = mapped_column(String(20), default="USER")
    subject_id = mapped_column(uuid_column(), index=True)
    role: Mapped[str] = mapped_column(String(20))
    granted_by = mapped_column(uuid_column(), ForeignKey("users.id"))
    expires_at = mapped_column(UTCDateTime(), nullable=True)
    created_at = mapped_column(UTCDateTime())


class ShareLinkModel(Base):
    __tablename__ = "share_links"

    id = mapped_column(uuid_column(), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(40))
    resource_id = mapped_column(uuid_column(), index=True)
    resource_version_id = mapped_column(uuid_column(), nullable=True)
    allowed_artifact_kinds = mapped_column(json_column())
    created_by = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    expires_at = mapped_column(UTCDateTime())
    revoked_at = mapped_column(UTCDateTime(), nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at = mapped_column(UTCDateTime(), nullable=True)
    created_at = mapped_column(UTCDateTime())


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id = mapped_column(uuid_column(), primary_key=True)
    actor_id = mapped_column(uuid_column(), ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resource_id = mapped_column(uuid_column(), nullable=True)
    details = mapped_column(json_column())
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at = mapped_column(UTCDateTime(), index=True)
