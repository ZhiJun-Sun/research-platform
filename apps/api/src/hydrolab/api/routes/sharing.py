"""分享链接路由（/share-links, /shared/{token}）。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from hydrolab.api.schemas import (
    CreateShareLinkRequest,
    CreateShareLinkResponse,
    SharedResourceView,
    ShareLinkView,
)
from hydrolab.auth.dependencies import get_current_user
from hydrolab.core.settings import get_settings
from hydrolab.domain.entities import ShareLink, User

router = APIRouter(tags=["sharing"])


def _link_view(link: ShareLink) -> ShareLinkView:
    return ShareLinkView(
        id=link.id,
        resource_type=link.resource_type,
        resource_id=link.resource_id,
        resource_version_id=link.resource_version_id,
        allowed_artifact_kinds=link.allowed_artifact_kinds,
        expires_at=link.expires_at,
        revoked_at=link.revoked_at,
        access_count=link.access_count,
        last_accessed_at=link.last_accessed_at,
        created_at=link.created_at,
    )


@router.post("/share-links", response_model=CreateShareLinkResponse, status_code=201)
async def create_share_link(
    body: CreateShareLinkRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> CreateShareLinkResponse:
    idempotency_key = request.headers.get("idempotency-key")
    link, token = await request.app.state.share_service.create(
        user,
        body.resource_type,
        body.resource_id,
        resource_version_id=body.resource_version_id,
        allowed_artifact_kinds=body.allowed_artifact_kinds,
        expires_in_hours=body.expires_in_hours,
        idempotency_key=idempotency_key,
    )
    settings = get_settings()
    url = f"{settings.public_base_url}/api/v1/shared/{token}" if token else ""
    return CreateShareLinkResponse(share_link=_link_view(link), token=token, url=url)


@router.get("/share-links", response_model=list[ShareLinkView])
async def list_share_links(
    request: Request, user: User = Depends(get_current_user)
) -> list[ShareLinkView]:
    links = await request.app.state.share_service.list_mine(user)
    return [_link_view(link) for link in links]


@router.post("/share-links/{link_id}/revoke", response_model=ShareLinkView)
async def revoke_share_link(
    link_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> ShareLinkView:
    link = await request.app.state.share_service.revoke(user, link_id)
    return _link_view(link)


@router.get("/shared/{token}", response_model=SharedResourceView)
async def access_shared(token: str, request: Request) -> SharedResourceView:
    # 防枚举限流：按客户端 + token 计数
    client = request.client.host if request.client else "unknown"
    request.app.state.shared_rate_limiter.check(f"{client}:{token[:8]}")
    link = await request.app.state.share_service.access(token)
    return SharedResourceView(
        resource_type=link.resource_type,
        resource_id=link.resource_id,
        resource_version_id=link.resource_version_id,
        allowed_artifact_kinds=link.allowed_artifact_kinds,
        expires_at=link.expires_at,
    )
