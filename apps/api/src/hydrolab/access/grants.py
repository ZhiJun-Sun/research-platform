"""授权管理应用服务：资源 Owner 授予/撤销其他用户角色。"""

from uuid import UUID

from hydrolab.access.policy import AccessPolicy
from hydrolab.core.errors import conflict, not_found
from hydrolab.domain.entities import AuditLog, ResourceGrant, User
from hydrolab.domain.enums import AuditAction, ResourceType, Role
from hydrolab.repositories import AuditLogRepository, GrantRepository, UserRepository


class GrantService:
    def __init__(
        self,
        grants: GrantRepository,
        users: UserRepository,
        policy: AccessPolicy,
        audit: AuditLogRepository,
    ) -> None:
        self._grants = grants
        self._users = users
        self._policy = policy
        self._audit = audit

    async def grant_role(
        self,
        actor: User,
        resource_type: ResourceType,
        resource_id: UUID,
        target_email: str,
        role: Role,
    ) -> ResourceGrant:
        await self._policy.require(actor, resource_type, resource_id, Role.OWNER)
        target = await self._users.get_by_email(target_email)
        if target is None:
            raise not_found("目标用户不存在")
        existing = await self._grants.get(resource_type, resource_id, target.id)
        if existing is not None:
            if existing.role == role:
                return existing
            existing.role = role
            await self._grants.add(existing)
            grant = existing
        else:
            grant = ResourceGrant(
                resource_type=resource_type,
                resource_id=resource_id,
                subject_id=target.id,
                role=role,
                granted_by=actor.id,
            )
            await self._grants.add(grant)
        await self._audit.add(
            AuditLog(
                actor_id=actor.id,
                action=AuditAction.GRANT_CREATED.value,
                resource_type=resource_type.value,
                resource_id=resource_id,
                details={"target_user_id": str(target.id), "role": role.value},
            )
        )
        return grant

    async def revoke(
        self, actor: User, resource_type: ResourceType, resource_id: UUID, grant_id: UUID
    ) -> None:
        await self._policy.require(actor, resource_type, resource_id, Role.OWNER)
        grant = await self._grants.get_by_id(grant_id)
        if (
            grant is None
            or grant.resource_type != resource_type
            or grant.resource_id != resource_id
        ):
            raise not_found("授权不存在")
        if grant.role == Role.OWNER and grant.subject_id == actor.id:
            raise conflict("不能撤销自己的所有者权限")
        await self._grants.delete(grant_id)
        await self._audit.add(
            AuditLog(
                actor_id=actor.id,
                action=AuditAction.GRANT_REVOKED.value,
                resource_type=resource_type.value,
                resource_id=resource_id,
                details={"revoked_grant_id": str(grant_id)},
            )
        )

    async def list_grants(
        self, actor: User, resource_type: ResourceType, resource_id: UUID
    ) -> list[ResourceGrant]:
        await self._policy.require(actor, resource_type, resource_id, Role.OWNER)
        return await self._grants.list_for_resource(resource_type, resource_id)
