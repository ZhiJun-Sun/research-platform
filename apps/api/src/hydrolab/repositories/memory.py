"""InMemory Repository 实现。

- 进程内字典存储，供无数据库环境开发与联调；
- 真实部署时由 SQL 实现替换（Alembic 迁移已在 B0 就绪）；
- 注意：进程重启数据丢失，仅用于 local/test。
"""

from uuid import UUID

from hydrolab.domain.entities import (
    AuditLog,
    Invitation,
    ResourceGrant,
    Session,
    ShareLink,
    User,
)
from hydrolab.domain.enums import ResourceType


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._users: dict[UUID, User] = {}

    async def add(self, user: User) -> User:
        self._users[user.id] = user
        return user

    async def get(self, user_id: UUID) -> User | None:
        return self._users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        lowered = email.lower()
        return next((u for u in self._users.values() if u.email.lower() == lowered), None)

    async def update(self, user: User) -> User:
        self._users[user.id] = user
        return user

    async def count(self) -> int:
        return len(self._users)


class InMemoryInvitationRepository:
    def __init__(self) -> None:
        self._invitations: dict[UUID, Invitation] = {}

    async def add(self, invitation: Invitation) -> Invitation:
        self._invitations[invitation.id] = invitation
        return invitation

    async def get(self, invitation_id: UUID) -> Invitation | None:
        return self._invitations.get(invitation_id)

    async def get_by_token_hash(self, token_hash: str) -> Invitation | None:
        return next(
            (i for i in self._invitations.values() if i.token_hash == token_hash), None
        )

    async def update(self, invitation: Invitation) -> Invitation:
        self._invitations[invitation.id] = invitation
        return invitation

    async def list_pending(self) -> list[Invitation]:
        return sorted(self._invitations.values(), key=lambda i: i.created_at, reverse=True)


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[UUID, Session] = {}

    async def add(self, session: Session) -> Session:
        self._sessions[session.id] = session
        return session

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        return next((s for s in self._sessions.values() if s.token_hash == token_hash), None)

    async def get_by_refresh_hash(self, refresh_hash: str) -> Session | None:
        return next(
            (s for s in self._sessions.values() if s.refresh_token_hash == refresh_hash), None
        )

    async def update(self, session: Session) -> Session:
        self._sessions[session.id] = session
        return session


class InMemoryGrantRepository:
    def __init__(self) -> None:
        self._grants: dict[UUID, ResourceGrant] = {}

    async def add(self, grant: ResourceGrant) -> ResourceGrant:
        self._grants[grant.id] = grant
        return grant

    async def delete(self, grant_id: UUID) -> bool:
        return self._grants.pop(grant_id, None) is not None

    async def get(
        self, resource_type: ResourceType, resource_id: UUID, subject_id: UUID
    ) -> ResourceGrant | None:
        return next(
            (
                g
                for g in self._grants.values()
                if g.resource_type == resource_type
                and g.resource_id == resource_id
                and g.subject_id == subject_id
            ),
            None,
        )

    async def get_by_id(self, grant_id: UUID) -> ResourceGrant | None:
        return self._grants.get(grant_id)

    async def list_for_resource(
        self, resource_type: ResourceType, resource_id: UUID
    ) -> list[ResourceGrant]:
        return [
            g
            for g in self._grants.values()
            if g.resource_type == resource_type and g.resource_id == resource_id
        ]


class InMemoryShareLinkRepository:
    def __init__(self) -> None:
        self._links: dict[UUID, ShareLink] = {}

    async def add(self, link: ShareLink) -> ShareLink:
        self._links[link.id] = link
        return link

    async def get(self, link_id: UUID) -> ShareLink | None:
        return self._links.get(link_id)

    async def get_by_token_hash(self, token_hash: str) -> ShareLink | None:
        return next((link for link in self._links.values() if link.token_hash == token_hash), None)

    async def update(self, link: ShareLink) -> ShareLink:
        self._links[link.id] = link
        return link

    async def list_by_creator(self, user_id: UUID) -> list[ShareLink]:
        return sorted(
            (link for link in self._links.values() if link.created_by == user_id),
            key=lambda link: link.created_at,
            reverse=True,
        )


class InMemoryAuditLogRepository:
    def __init__(self) -> None:
        self._entries: list[AuditLog] = []

    async def add(self, entry: AuditLog) -> AuditLog:
        self._entries.append(entry)
        return entry

    async def list_recent(self, limit: int = 100) -> list[AuditLog]:
        return self._entries[-limit:][::-1]
