"""资源授权路由（/resources/{type}/{id}/grants）。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from hydrolab.api.schemas import CreateGrantRequest, GrantView
from hydrolab.auth.dependencies import get_current_user
from hydrolab.domain.entities import ResourceGrant, User
from hydrolab.domain.enums import ResourceType

router = APIRouter(tags=["grants"])


def _grant_view(grant: ResourceGrant) -> GrantView:
    return GrantView(
        id=grant.id,
        resource_type=grant.resource_type,
        resource_id=grant.resource_id,
        subject_id=grant.subject_id,
        role=grant.role,
        expires_at=grant.expires_at,
        created_at=grant.created_at,
    )


@router.get(
    "/resources/{resource_type}/{resource_id}/grants", response_model=list[GrantView]
)
async def list_grants(
    resource_type: ResourceType,
    resource_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> list[GrantView]:
    grants = await request.app.state.grant_service.list_grants(user, resource_type, resource_id)
    return [_grant_view(g) for g in grants]


@router.post(
    "/resources/{resource_type}/{resource_id}/grants",
    response_model=GrantView,
    status_code=201,
)
async def create_grant(
    resource_type: ResourceType,
    resource_id: UUID,
    body: CreateGrantRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> GrantView:
    grant = await request.app.state.grant_service.grant_role(
        user, resource_type, resource_id, body.email, body.role
    )
    return _grant_view(grant)


@router.delete("/resources/{resource_type}/{resource_id}/grants/{grant_id}", status_code=204)
async def revoke_grant(
    resource_type: ResourceType,
    resource_id: UUID,
    grant_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    await request.app.state.grant_service.revoke(user, resource_type, resource_id, grant_id)
