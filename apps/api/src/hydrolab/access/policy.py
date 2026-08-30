"""资源授权 Policy（plans/02 第 3.2 节）。

- 业务查询先过 Policy，再访问资源；禁止只依赖前端隐藏按钮；
- 首版角色：OWNER / VIEWER；管理员可读取但不自动获得管理操作权之外的资源所有权；
- 授权有过期时间支持。
"""

from uuid import UUID

from hydrolab.core.errors import forbidden
from hydrolab.domain.entities import ResourceGrant, User, utcnow
from hydrolab.domain.enums import ResourceType, Role
from hydrolab.repositories import GrantRepository

_ROLE_RANK = {Role.VIEWER: 1, Role.OWNER: 2}


class AccessPolicy:
    def __init__(self, grants: GrantRepository) -> None:
        self._grants = grants

    async def role_of(
        self, user: User, resource_type: ResourceType, resource_id: UUID
    ) -> Role | None:
        grant = await self._grants.get(resource_type, resource_id, user.id)
        if grant is None:
            return None
        if grant.expires_at is not None and grant.expires_at <= utcnow():
            return None
        return grant.role

    async def can_read(self, user: User, resource_type: ResourceType, resource_id: UUID) -> bool:
        if user.is_admin:
            return True
        return await self.role_of(user, resource_type, resource_id) is not None

    async def require(
        self,
        user: User,
        resource_type: ResourceType,
        resource_id: UUID,
        minimum: Role,
    ) -> ResourceGrant | None:
        """不足权限抛 FORBIDDEN；返回用户的 grant（管理员为 None）。"""
        if user.is_admin:
            return None
        role = await self.role_of(user, resource_type, resource_id)
        if role is None or _ROLE_RANK[role] < _ROLE_RANK[minimum]:
            raise forbidden("无权访问该资源")
        return await self._grants.get(resource_type, resource_id, user.id)
