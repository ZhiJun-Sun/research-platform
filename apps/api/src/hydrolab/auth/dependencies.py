"""认证依赖：从 Authorization: Bearer 解析当前用户。"""

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from hydrolab.auth.service import AuthService
from hydrolab.core.errors import forbidden, unauthenticated
from hydrolab.domain.entities import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthenticated("缺少 Bearer 凭证")
    service: AuthService = request.app.state.auth_service
    return await service.authenticate(credentials.credentials)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise forbidden("需要管理员权限")
    return user
