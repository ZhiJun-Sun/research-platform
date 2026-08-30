"""邀请管理路由（/admin/invitations, /invitations/{token}/accept）。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from hydrolab.api.schemas import (
    AcceptInvitationRequest,
    CreateInvitationRequest,
    CreateInvitationResponse,
    InvitationView,
    LoginResponse,
    TokenPairView,
    UserView,
)
from hydrolab.auth.dependencies import require_admin
from hydrolab.domain.entities import Invitation, User

router = APIRouter(tags=["invitations"])


def _invitation_view(invitation: Invitation) -> InvitationView:
    return InvitationView(
        id=invitation.id,
        email=invitation.email,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        revoked_at=invitation.revoked_at,
        created_at=invitation.created_at,
    )


@router.post("/admin/invitations", response_model=CreateInvitationResponse, status_code=201)
async def create_invitation(
    body: CreateInvitationRequest,
    request: Request,
    admin: User = Depends(require_admin),
) -> CreateInvitationResponse:
    invitation, token = await request.app.state.auth_service.create_invitation(
        admin, body.email, body.expires_in_hours
    )
    return CreateInvitationResponse(invitation=_invitation_view(invitation), token=token)


@router.get("/admin/invitations", response_model=list[InvitationView])
async def list_invitations(
    request: Request, admin: User = Depends(require_admin)
) -> list[InvitationView]:
    invitations = await request.app.state.repos.invitations.list_pending()
    return [_invitation_view(i) for i in invitations]


@router.post("/admin/invitations/{invitation_id}/revoke", response_model=InvitationView)
async def revoke_invitation(
    invitation_id: UUID,
    request: Request,
    admin: User = Depends(require_admin),
) -> InvitationView:
    invitation = await request.app.state.auth_service.revoke_invitation(admin, invitation_id)
    return _invitation_view(invitation)


@router.post("/invitations/{token}/accept", response_model=LoginResponse, status_code=201)
async def accept_invitation(
    token: str, body: AcceptInvitationRequest, request: Request
) -> LoginResponse:
    user, pair = await request.app.state.auth_service.accept_invitation(
        token, body.display_name, body.password
    )
    return LoginResponse(
        user=UserView(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_admin=user.is_admin,
            status=user.status,
            created_at=user.created_at,
        ),
        tokens=TokenPairView(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            expires_in=pair.expires_in,
        ),
    )
