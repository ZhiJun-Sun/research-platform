"""认证与当前用户路由（/auth/*, /me）。"""

from fastapi import APIRouter, Depends, Request

from hydrolab.api.schemas import (
    LoginRequest,
    LoginResponse,
    PreferencesView,
    RefreshRequest,
    TokenPairView,
    UpdatePreferencesRequest,
    UserView,
)
from hydrolab.auth.dependencies import get_current_user
from hydrolab.auth.service import TokenPair
from hydrolab.domain.entities import User

router = APIRouter(tags=["auth"])


def _user_view(user: User) -> UserView:
    return UserView(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        status=user.status,
        created_at=user.created_at,
    )


def _tokens_view(pair: TokenPair) -> TokenPairView:
    return TokenPairView(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    user, pair = await request.app.state.auth_service.login(
        body.email, body.password, request_id=request.state.request_id
    )
    return LoginResponse(user=_user_view(user), tokens=_tokens_view(pair))


@router.post("/auth/refresh", response_model=LoginResponse)
async def refresh(body: RefreshRequest, request: Request) -> LoginResponse:
    user, pair = await request.app.state.auth_service.refresh(body.refresh_token)
    return LoginResponse(user=_user_view(user), tokens=_tokens_view(pair))


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, user: User = Depends(get_current_user)) -> None:
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    await request.app.state.auth_service.logout(token)


@router.get("/me", response_model=UserView)
async def me(user: User = Depends(get_current_user)) -> UserView:
    return _user_view(user)


@router.get("/me/preferences", response_model=PreferencesView)
async def get_preferences(user: User = Depends(get_current_user)) -> PreferencesView:
    return PreferencesView(preferences=user.preferences)


@router.patch("/me/preferences", response_model=PreferencesView)
async def update_preferences(
    body: UpdatePreferencesRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> PreferencesView:
    user.preferences = body.preferences
    await request.app.state.repos.users.update(user)
    return PreferencesView(preferences=user.preferences)
