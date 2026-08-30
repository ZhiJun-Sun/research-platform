"""只读分享链接应用服务（plans/02 第 3.3、6.8 节）。

- 原始 token 仅创建时返回一次，存储 HMAC 哈希；
- 链接锁定资源版本，支持过期与撤销（撤销幂等且立即生效）；
- 公开访问递增计数并写审计；字段白名单在路由层控制；
- 创建支持 Idempotency-Key。
"""

from datetime import timedelta
from uuid import UUID

from hydrolab.access.policy import AccessPolicy
from hydrolab.auth.tokens import generate_token, hash_token
from hydrolab.core.errors import AppError, forbidden, not_found, validation_error
from hydrolab.core.idempotency import InMemoryIdempotencyStore
from hydrolab.core.settings import Settings
from hydrolab.domain.entities import AuditLog, ShareLink, User, utcnow
from hydrolab.domain.enums import AuditAction, ResourceType, Role
from hydrolab.repositories import AuditLogRepository, ShareLinkRepository

MAX_EXPIRES_HOURS = 24 * 30  # 最长 30 天


class ShareService:
    def __init__(
        self,
        links: ShareLinkRepository,
        policy: AccessPolicy,
        audit: AuditLogRepository,
        settings: Settings,
        idempotency: InMemoryIdempotencyStore,
    ) -> None:
        self._links = links
        self._policy = policy
        self._audit = audit
        self._settings = settings
        self._idempotency = idempotency

    async def create(
        self,
        actor: User,
        resource_type: ResourceType,
        resource_id: UUID,
        *,
        resource_version_id: UUID | None = None,
        allowed_artifact_kinds: list[str] | None = None,
        expires_in_hours: int = 24 * 7,
        idempotency_key: str | None = None,
    ) -> tuple[ShareLink, str | None]:
        """返回 (link, raw_token)。幂等命中时 raw_token 为 None（原文不重复下发）。"""
        if idempotency_key:
            existing_id = self._idempotency.get(f"share:{actor.id}", idempotency_key)
            if existing_id is not None:
                existing = await self._links.get(existing_id)
                if existing is not None:
                    return existing, None

        await self._policy.require(actor, resource_type, resource_id, Role.OWNER)
        if not (1 <= expires_in_hours <= MAX_EXPIRES_HOURS):
            raise validation_error(
                "有效期超出范围", {"max_hours": MAX_EXPIRES_HOURS, "given": expires_in_hours}
            )
        token = generate_token()
        link = ShareLink(
            token_hash=hash_token(token, self._settings.auth_secret),
            resource_type=resource_type,
            resource_id=resource_id,
            resource_version_id=resource_version_id,
            allowed_artifact_kinds=allowed_artifact_kinds or [],
            created_by=actor.id,
            expires_at=utcnow() + timedelta(hours=expires_in_hours),
        )
        await self._links.add(link)
        if idempotency_key:
            self._idempotency.put(f"share:{actor.id}", idempotency_key, link.id)
        await self._audit.add(
            AuditLog(
                actor_id=actor.id,
                action=AuditAction.SHARE_LINK_CREATED.value,
                resource_type=resource_type.value,
                resource_id=resource_id,
                details={"share_link_id": str(link.id), "expires_at": link.expires_at.isoformat()},
            )
        )
        return link, token

    async def list_mine(self, actor: User) -> list[ShareLink]:
        return await self._links.list_by_creator(actor.id)

    async def revoke(self, actor: User, link_id: UUID) -> ShareLink:
        link = await self._links.get(link_id)
        if link is None:
            raise not_found("分享链接不存在")
        if link.created_by != actor.id and not actor.is_admin:
            raise forbidden("只能撤销自己创建的分享链接")
        if link.revoked_at is None:
            link.revoked_at = utcnow()
            await self._links.update(link)
            await self._audit.add(
                AuditLog(
                    actor_id=actor.id,
                    action=AuditAction.SHARE_LINK_REVOKED.value,
                    resource_type=link.resource_type.value,
                    resource_id=link.resource_id,
                    details={"share_link_id": str(link.id)},
                )
            )
        return link

    async def access(self, token: str) -> ShareLink:
        """公开访问：验证有效性并记录访问。不返回任何凭证信息。"""
        link = await self._links.get_by_token_hash(
            hash_token(token, self._settings.auth_secret)
        )
        if link is None:
            raise not_found("分享链接不存在")
        now = utcnow()
        if link.revoked_at is not None:
            raise AppError("SHARE_LINK_REVOKED", "分享链接已被撤销", status_code=410)
        if link.expires_at <= now:
            raise AppError("SHARE_LINK_EXPIRED", "分享链接已过期", status_code=410)
        link.access_count += 1
        link.last_accessed_at = now
        await self._links.update(link)
        await self._audit.add(
            AuditLog(
                actor_id=None,
                action=AuditAction.SHARE_LINK_ACCESSED.value,
                resource_type=link.resource_type.value,
                resource_id=link.resource_id,
                details={"share_link_id": str(link.id)},
            )
        )
        return link
