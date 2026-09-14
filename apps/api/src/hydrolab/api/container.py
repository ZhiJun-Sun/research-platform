"""应用状态容器：Repository 与服务装配。

B1 使用 InMemory Repository（无数据库联调基线）；
接入 PostgreSQL 时仅替换此处的构造实现。
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hydrolab.access.grants import GrantService
from hydrolab.access.policy import AccessPolicy
from hydrolab.auth.service import AuthService
from hydrolab.core.idempotency import InMemoryIdempotencyStore
from hydrolab.core.settings import Settings
from hydrolab.repositories import (
    AuditLogRepository,
    GrantRepository,
    InvitationRepository,
    SessionRepository,
    ShareLinkRepository,
    UserRepository,
)
from hydrolab.repositories.memory import (
    InMemoryAuditLogRepository,
    InMemoryGrantRepository,
    InMemoryInvitationRepository,
    InMemorySessionRepository,
    InMemoryShareLinkRepository,
    InMemoryUserRepository,
)
from hydrolab.sharing.service import ShareService

if TYPE_CHECKING:
    pass


@dataclass
class Repositories:
    users: UserRepository
    invitations: InvitationRepository
    sessions: SessionRepository
    grants: GrantRepository
    share_links: ShareLinkRepository
    audit: AuditLogRepository


@dataclass
class AppServices:
    repos: Repositories
    auth: AuthService
    policy: AccessPolicy
    grants: GrantService
    share: ShareService


def build_repositories(session_factory=None) -> Repositories:
    if session_factory is not None:
        from hydrolab.db.repositories.identity import (
            SqlAuditLogRepository,
            SqlGrantRepository,
            SqlInvitationRepository,
            SqlSessionRepository,
            SqlShareLinkRepository,
            SqlUserRepository,
        )

        return Repositories(
            users=SqlUserRepository(session_factory),
            invitations=SqlInvitationRepository(session_factory),
            sessions=SqlSessionRepository(session_factory),
            grants=SqlGrantRepository(session_factory),
            share_links=SqlShareLinkRepository(session_factory),
            audit=SqlAuditLogRepository(session_factory),
        )
    return Repositories(
        users=InMemoryUserRepository(),
        invitations=InMemoryInvitationRepository(),
        sessions=InMemorySessionRepository(),
        grants=InMemoryGrantRepository(),
        share_links=InMemoryShareLinkRepository(),
        audit=InMemoryAuditLogRepository(),
    )


def build_services(settings: Settings, repos: Repositories) -> AppServices:
    policy = AccessPolicy(repos.grants)
    auth = AuthService(repos.users, repos.invitations, repos.sessions, repos.audit, settings)
    grants = GrantService(repos.grants, repos.users, policy, repos.audit)
    share = ShareService(
        repos.share_links, policy, repos.audit, settings, InMemoryIdempotencyStore()
    )
    return AppServices(repos=repos, auth=auth, policy=policy, grants=grants, share=share)
