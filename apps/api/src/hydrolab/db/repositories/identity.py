"""B1 身份、授权领域 SQL 仓储（实现 repositories/__init__.py 的 Protocol）。"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hydrolab.db.models.identity import (
    AuditLogModel,
    GrantModel,
    InvitationModel,
    SessionModel,
    ShareLinkModel,
    UserModel,
)
from hydrolab.db.unit_of_work import commit_or_defer, session_scope
from hydrolab.domain.entities import (
    AuditLog,
    Invitation,
    ResourceGrant,
    Session,
    ShareLink,
    User,
)
from hydrolab.domain.enums import ResourceType, Role, SubjectType, UserStatus


def _to_user(m: UserModel) -> User:
    return User(
        id=m.id,
        email=m.email,
        display_name=m.display_name,
        password_hash=m.password_hash,
        status=UserStatus(m.status),
        is_admin=m.is_admin,
        preferences=m.preferences or {},
        created_at=m.created_at,
    )


def _to_invitation(m: InvitationModel) -> Invitation:
    return Invitation(
        id=m.id,
        token_hash=m.token_hash,
        email=m.email,
        inviter_id=m.inviter_id,
        expires_at=m.expires_at,
        accepted_at=m.accepted_at,
        revoked_at=m.revoked_at,
        created_at=m.created_at,
    )


def _to_session(m: SessionModel) -> Session:
    return Session(
        id=m.id,
        user_id=m.user_id,
        token_hash=m.token_hash,
        refresh_token_hash=m.refresh_token_hash,
        expires_at=m.expires_at,
        refresh_expires_at=m.refresh_expires_at,
        revoked_at=m.revoked_at,
        created_at=m.created_at,
    )


def _to_grant(m: GrantModel) -> ResourceGrant:
    return ResourceGrant(
        id=m.id,
        resource_type=ResourceType(m.resource_type),
        resource_id=m.resource_id,
        subject_type=SubjectType(m.subject_type),
        subject_id=m.subject_id,
        role=Role(m.role),
        granted_by=m.granted_by,
        expires_at=m.expires_at,
        created_at=m.created_at,
    )


def _to_share_link(m: ShareLinkModel) -> ShareLink:
    return ShareLink(
        id=m.id,
        token_hash=m.token_hash,
        resource_type=ResourceType(m.resource_type),
        resource_id=m.resource_id,
        resource_version_id=m.resource_version_id,
        allowed_artifact_kinds=m.allowed_artifact_kinds or [],
        created_by=m.created_by,
        expires_at=m.expires_at,
        revoked_at=m.revoked_at,
        access_count=m.access_count,
        last_accessed_at=m.last_accessed_at,
        created_at=m.created_at,
    )


def _to_audit(m: AuditLogModel) -> AuditLog:
    return AuditLog(
        id=m.id,
        actor_id=m.actor_id,
        action=m.action,
        resource_type=m.resource_type,
        resource_id=m.resource_id,
        details=m.details or {},
        request_id=m.request_id,
        created_at=m.created_at,
    )


class SqlUserRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, user: User) -> User:
        async with self._sf() as session:
            m = UserModel(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                password_hash=user.password_hash,
                status=user.status.value,
                is_admin=user.is_admin,
                preferences=user.preferences,
                created_at=user.created_at,
            )
            session.add(m)
            await session.commit()
            return user

    async def get(self, user_id: UUID) -> User | None:
        async with self._sf() as session:
            m = await session.get(UserModel, user_id)
            return _to_user(m) if m else None

    async def get_by_email(self, email: str) -> User | None:
        async with self._sf() as session:
            res = await session.execute(select(UserModel).where(UserModel.email == email.lower()))
            m = res.scalar_one_or_none()
            return _to_user(m) if m else None

    async def update(self, user: User) -> User:
        async with self._sf() as session:
            m = await session.get(UserModel, user.id)
            if m is None:
                return user
            m.email = user.email
            m.display_name = user.display_name
            m.password_hash = user.password_hash
            m.status = user.status.value
            m.is_admin = user.is_admin
            m.preferences = user.preferences
            await session.commit()
            return user

    async def count(self) -> int:
        async with self._sf() as session:
            res = await session.execute(select(func.count(UserModel.id)))
            return int(res.scalar_one())


class SqlInvitationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, invitation: Invitation) -> Invitation:
        async with self._sf() as session:
            session.add(
                InvitationModel(
                    id=invitation.id,
                    token_hash=invitation.token_hash,
                    email=invitation.email,
                    inviter_id=invitation.inviter_id,
                    expires_at=invitation.expires_at,
                    accepted_at=invitation.accepted_at,
                    revoked_at=invitation.revoked_at,
                    created_at=invitation.created_at,
                )
            )
            await session.commit()
            return invitation

    async def get(self, invitation_id: UUID) -> Invitation | None:
        async with self._sf() as session:
            m = await session.get(InvitationModel, invitation_id)
            return _to_invitation(m) if m else None

    async def get_by_token_hash(self, token_hash: str) -> Invitation | None:
        async with self._sf() as session:
            res = await session.execute(
                select(InvitationModel).where(InvitationModel.token_hash == token_hash)
            )
            m = res.scalar_one_or_none()
            return _to_invitation(m) if m else None

    async def update(self, invitation: Invitation) -> Invitation:
        async with self._sf() as session:
            m = await session.get(InvitationModel, invitation.id)
            if m is None:
                return invitation
            m.accepted_at = invitation.accepted_at
            m.revoked_at = invitation.revoked_at
            await session.commit()
            return invitation

    async def list_pending(self) -> list[Invitation]:
        async with self._sf() as session:
            res = await session.execute(
                select(InvitationModel)
                .where(InvitationModel.accepted_at.is_(None), InvitationModel.revoked_at.is_(None))
                .order_by(InvitationModel.created_at.desc())
            )
            return [_to_invitation(m) for m in res.scalars().all()]


class SqlSessionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, session: Session) -> Session:
        async with self._sf() as db:
            db.add(
                SessionModel(
                    id=session.id,
                    user_id=session.user_id,
                    token_hash=session.token_hash,
                    refresh_token_hash=session.refresh_token_hash,
                    expires_at=session.expires_at,
                    refresh_expires_at=session.refresh_expires_at,
                    revoked_at=session.revoked_at,
                    created_at=session.created_at,
                )
            )
            await db.commit()
            return session

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        async with self._sf() as db:
            res = await db.execute(
                select(SessionModel).where(SessionModel.token_hash == token_hash)
            )
            m = res.scalar_one_or_none()
            return _to_session(m) if m else None

    async def get_by_refresh_hash(self, refresh_hash: str) -> Session | None:
        async with self._sf() as db:
            res = await db.execute(
                select(SessionModel).where(SessionModel.refresh_token_hash == refresh_hash)
            )
            m = res.scalar_one_or_none()
            return _to_session(m) if m else None

    async def update(self, session: Session) -> Session:
        async with self._sf() as db:
            m = await db.get(SessionModel, session.id)
            if m is None:
                return session
            m.token_hash = session.token_hash
            m.refresh_token_hash = session.refresh_token_hash
            m.expires_at = session.expires_at
            m.refresh_expires_at = session.refresh_expires_at
            m.revoked_at = session.revoked_at
            await db.commit()
            return session


class SqlGrantRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, grant: ResourceGrant) -> ResourceGrant:
        async with session_scope(self._sf) as db:
            db.add(
                GrantModel(
                    id=grant.id,
                    resource_type=grant.resource_type.value,
                    resource_id=grant.resource_id,
                    subject_type=grant.subject_type.value,
                    subject_id=grant.subject_id,
                    role=grant.role.value,
                    granted_by=grant.granted_by,
                    expires_at=grant.expires_at,
                    created_at=grant.created_at,
                )
            )
            await commit_or_defer(db)
            return grant

    async def delete(self, grant_id: UUID) -> bool:
        async with self._sf() as db:
            m = await db.get(GrantModel, grant_id)
            if m is None:
                return False
            await db.delete(m)
            await db.commit()
            return True

    async def get(
        self, resource_type: ResourceType, resource_id: UUID, subject_id: UUID
    ) -> ResourceGrant | None:
        async with self._sf() as db:
            res = await db.execute(
                select(GrantModel).where(
                    GrantModel.resource_type == resource_type.value,
                    GrantModel.resource_id == resource_id,
                    GrantModel.subject_id == subject_id,
                )
            )
            m = res.scalar_one_or_none()
            return _to_grant(m) if m else None

    async def get_by_id(self, grant_id: UUID) -> ResourceGrant | None:
        async with self._sf() as db:
            m = await db.get(GrantModel, grant_id)
            return _to_grant(m) if m else None

    async def list_for_resource(
        self, resource_type: ResourceType, resource_id: UUID
    ) -> list[ResourceGrant]:
        async with self._sf() as db:
            res = await db.execute(
                select(GrantModel).where(
                    GrantModel.resource_type == resource_type.value,
                    GrantModel.resource_id == resource_id,
                )
            )
            return [_to_grant(m) for m in res.scalars().all()]


class SqlShareLinkRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, link: ShareLink) -> ShareLink:
        async with self._sf() as db:
            db.add(
                ShareLinkModel(
                    id=link.id,
                    token_hash=link.token_hash,
                    resource_type=link.resource_type.value,
                    resource_id=link.resource_id,
                    resource_version_id=link.resource_version_id,
                    allowed_artifact_kinds=link.allowed_artifact_kinds,
                    created_by=link.created_by,
                    expires_at=link.expires_at,
                    revoked_at=link.revoked_at,
                    access_count=link.access_count,
                    last_accessed_at=link.last_accessed_at,
                    created_at=link.created_at,
                )
            )
            await db.commit()
            return link

    async def get(self, link_id: UUID) -> ShareLink | None:
        async with self._sf() as db:
            m = await db.get(ShareLinkModel, link_id)
            return _to_share_link(m) if m else None

    async def get_by_token_hash(self, token_hash: str) -> ShareLink | None:
        async with self._sf() as db:
            res = await db.execute(
                select(ShareLinkModel).where(ShareLinkModel.token_hash == token_hash)
            )
            m = res.scalar_one_or_none()
            return _to_share_link(m) if m else None

    async def update(self, link: ShareLink) -> ShareLink:
        async with self._sf() as db:
            m = await db.get(ShareLinkModel, link.id)
            if m is None:
                return link
            m.revoked_at = link.revoked_at
            m.access_count = link.access_count
            m.last_accessed_at = link.last_accessed_at
            await db.commit()
            return link

    async def list_by_creator(self, user_id: UUID) -> list[ShareLink]:
        async with self._sf() as db:
            res = await db.execute(
                select(ShareLinkModel)
                .where(ShareLinkModel.created_by == user_id)
                .order_by(ShareLinkModel.created_at.desc())
            )
            return [_to_share_link(m) for m in res.scalars().all()]


class SqlAuditLogRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, entry: AuditLog) -> AuditLog:
        async with self._sf() as db:
            db.add(
                AuditLogModel(
                    id=entry.id,
                    actor_id=entry.actor_id,
                    action=entry.action,
                    resource_type=entry.resource_type,
                    resource_id=entry.resource_id,
                    details=entry.details,
                    request_id=entry.request_id,
                    created_at=entry.created_at,
                )
            )
            await db.commit()
            return entry

    async def list_recent(self, limit: int = 100) -> list[AuditLog]:
        async with self._sf() as db:
            res = await db.execute(
                select(AuditLogModel).order_by(AuditLogModel.created_at.desc()).limit(limit)
            )
            return [_to_audit(m) for m in res.scalars().all()]


__all__ = [
    "SqlAuditLogRepository",
    "SqlGrantRepository",
    "SqlInvitationRepository",
    "SqlSessionRepository",
    "SqlShareLinkRepository",
    "SqlUserRepository",
]
