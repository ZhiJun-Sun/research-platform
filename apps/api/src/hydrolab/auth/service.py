"""认证与邀请应用服务（plans/02 第 3.1、6.1 节）。

- 无公开注册：仅管理员邀请；首个管理员通过 bootstrap 创建；
- 会话为不透明 access/refresh token，存储哈希；
- 所有凭证相关分支写审计日志（不含明文凭证）。
"""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from hydrolab.auth.passwords import hash_password, validate_password_strength, verify_password
from hydrolab.auth.tokens import generate_token, hash_token
from hydrolab.core.errors import AppError, conflict, unauthenticated, validation_error
from hydrolab.core.settings import Settings
from hydrolab.domain.entities import AuditLog, Invitation, Session, User, utcnow
from hydrolab.domain.enums import AuditAction, UserStatus
from hydrolab.repositories import (
    AuditLogRepository,
    InvitationRepository,
    SessionRepository,
    UserRepository,
)

ACCESS_TOKEN_TTL = timedelta(minutes=30)
REFRESH_TOKEN_TTL = timedelta(days=14)
INVITATION_DEFAULT_TTL = timedelta(hours=72)


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int  # access token 秒数


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        invitations: InvitationRepository,
        sessions: SessionRepository,
        audit: AuditLogRepository,
        settings: Settings,
    ) -> None:
        self._users = users
        self._invitations = invitations
        self._sessions = sessions
        self._audit = audit
        self._settings = settings

    # ---------- bootstrap ----------
    async def bootstrap_admin(self, email: str, password: str, display_name: str) -> User | None:
        """仅当系统没有任何用户时生效；返回 None 表示已初始化过。"""
        if await self._users.count() > 0:
            return None
        error = validate_password_strength(password)
        if error:
            raise validation_error(error)
        user = User(
            email=email.lower(),
            display_name=display_name,
            password_hash=hash_password(password),
            is_admin=True,
        )
        await self._users.add(user)
        await self._record(None, AuditAction.ADMIN_BOOTSTRAPPED, details={"email": user.email})
        return user

    # ---------- login / refresh / logout ----------
    async def login(
        self, email: str, password: str, request_id: str | None = None
    ) -> tuple[User, TokenPair]:
        user = await self._users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise unauthenticated("邮箱或密码错误")
        if user.status != UserStatus.ACTIVE:
            raise unauthenticated("账号已被禁用")
        pair = await self._issue_session(user.id)
        await self._record(user.id, AuditAction.USER_LOGIN, request_id=request_id)
        return user, pair

    async def refresh(self, refresh_token: str) -> tuple[User, TokenPair]:
        session = await self._sessions.get_by_refresh_hash(
            hash_token(refresh_token, self._settings.auth_secret)
        )
        now = utcnow()
        if session is None or session.revoked_at is not None or session.refresh_expires_at <= now:
            raise unauthenticated("refresh token 无效或已过期")
        user = await self._users.get(session.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise unauthenticated("账号不可用")
        session.revoked_at = now  # 旋转：旧会话立即失效
        await self._sessions.update(session)
        return user, await self._issue_session(user.id)

    async def logout(self, access_token: str) -> None:
        session = await self._sessions.get_by_token_hash(
            hash_token(access_token, self._settings.auth_secret)
        )
        if session and session.revoked_at is None:
            session.revoked_at = utcnow()
            await self._sessions.update(session)

    async def authenticate(self, access_token: str) -> User:
        session = await self._sessions.get_by_token_hash(
            hash_token(access_token, self._settings.auth_secret)
        )
        now = utcnow()
        if session is None or session.revoked_at is not None or session.expires_at <= now:
            raise unauthenticated("凭证无效或已过期")
        user = await self._users.get(session.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise unauthenticated("账号不可用")
        return user

    # ---------- invitations ----------
    async def create_invitation(
        self, inviter: User, email: str, expires_in_hours: int = 72
    ) -> tuple[Invitation, str]:
        email = email.lower()
        if await self._users.get_by_email(email):
            raise conflict("该邮箱已是注册用户", {"email": email})
        token = generate_token()
        invitation = Invitation(
            token_hash=hash_token(token, self._settings.auth_secret),
            email=email,
            inviter_id=inviter.id,
            expires_at=utcnow() + timedelta(hours=expires_in_hours),
        )
        await self._invitations.add(invitation)
        await self._record(
            inviter.id, AuditAction.INVITATION_CREATED, details={"email": email}
        )
        return invitation, token

    async def revoke_invitation(self, actor: User, invitation_id: UUID) -> Invitation:
        invitation = await self._invitations.get(invitation_id)
        if invitation is None:
            from hydrolab.core.errors import not_found

            raise not_found("邀请不存在")
        if invitation.revoked_at is None and invitation.accepted_at is None:
            invitation.revoked_at = utcnow()
            await self._invitations.update(invitation)
            await self._record(
                actor.id, AuditAction.INVITATION_REVOKED, details={"email": invitation.email}
            )
        return invitation

    async def accept_invitation(
        self, token: str, display_name: str, password: str
    ) -> tuple[User, TokenPair]:
        invitation = await self._invitations.get_by_token_hash(
            hash_token(token, self._settings.auth_secret)
        )
        now = utcnow()
        if invitation is None:
            raise AppError("INVITATION_INVALID", "邀请不存在或已被使用", status_code=404)
        if invitation.revoked_at is not None:
            raise AppError("INVITATION_INVALID", "邀请已被撤销", status_code=410)
        if invitation.accepted_at is not None:
            raise AppError("INVITATION_INVALID", "邀请已被使用", status_code=410)
        if invitation.expires_at <= now:
            raise AppError("INVITATION_EXPIRED", "邀请已过期", status_code=410)
        error = validate_password_strength(password)
        if error:
            raise validation_error(error)
        user = User(
            email=invitation.email,
            display_name=display_name,
            password_hash=hash_password(password),
        )
        await self._users.add(user)
        invitation.accepted_at = now
        await self._invitations.update(invitation)
        await self._record(
            user.id, AuditAction.INVITATION_ACCEPTED, details={"email": user.email}
        )
        return user, await self._issue_session(user.id)

    # ---------- helpers ----------
    async def _issue_session(self, user_id: UUID) -> TokenPair:
        access = generate_token()
        refresh = generate_token()
        now = utcnow()
        session = Session(
            user_id=user_id,
            token_hash=hash_token(access, self._settings.auth_secret),
            refresh_token_hash=hash_token(refresh, self._settings.auth_secret),
            expires_at=now + ACCESS_TOKEN_TTL,
            refresh_expires_at=now + REFRESH_TOKEN_TTL,
        )
        await self._sessions.add(session)
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
        )

    async def _record(
        self,
        actor_id: UUID | None,
        action: AuditAction,
        details: dict[str, object] | None = None,
        request_id: str | None = None,
    ) -> None:
        await self._audit.add(
            AuditLog(
                actor_id=actor_id,
                action=action.value,
                details=details or {},
                request_id=request_id,
            )
        )
