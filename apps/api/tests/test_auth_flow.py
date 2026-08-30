"""B1 认证流程测试：bootstrap、login、refresh、logout、/me。"""

from tests.conftest import DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD, TestContext, login


async def test_dev_admin_bootstrapped_and_login(ctx: TestContext) -> None:
    headers = await login(ctx, DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD)
    resp = await ctx.client.get("/api/v1/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == DEV_ADMIN_EMAIL
    assert body["is_admin"] is True
    assert "password" not in body
    assert "password_hash" not in body


async def test_login_wrong_password(ctx: TestContext) -> None:
    resp = await ctx.client.post(
        "/api/v1/auth/login", json={"email": DEV_ADMIN_EMAIL, "password": "wrong-password"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_me_requires_auth(ctx: TestContext) -> None:
    resp = await ctx.client.get("/api/v1/me")
    assert resp.status_code == 401


async def test_refresh_rotates_and_old_refresh_fails(ctx: TestContext) -> None:
    resp = await ctx.client.post(
        "/api/v1/auth/login", json={"email": DEV_ADMIN_EMAIL, "password": DEV_ADMIN_PASSWORD}
    )
    tokens = resp.json()["tokens"]

    resp = await ctx.client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    new_tokens = resp.json()["tokens"]
    assert new_tokens["access_token"] != tokens["access_token"]

    # 旧 refresh token 已旋转失效
    resp = await ctx.client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401


async def test_logout_invalidates_access_token(ctx: TestContext) -> None:
    headers = await login(ctx, DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD)
    resp = await ctx.client.post("/api/v1/auth/logout", headers=headers)
    assert resp.status_code == 204
    resp = await ctx.client.get("/api/v1/me", headers=headers)
    assert resp.status_code == 401


async def test_preferences_roundtrip(ctx: TestContext) -> None:
    headers = await login(ctx, DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD)
    prefs = {"run_detail_layout": ["gpu", "metrics"], "theme": "dark"}
    resp = await ctx.client.patch(
        "/api/v1/me/preferences", json={"preferences": prefs}, headers=headers
    )
    assert resp.status_code == 200
    resp = await ctx.client.get("/api/v1/me/preferences", headers=headers)
    assert resp.json()["preferences"] == prefs


async def test_session_stores_only_token_hashes(ctx: TestContext) -> None:
    resp = await ctx.client.post(
        "/api/v1/auth/login", json={"email": DEV_ADMIN_EMAIL, "password": DEV_ADMIN_PASSWORD}
    )
    raw_access = resp.json()["tokens"]["access_token"]
    sessions = ctx.app.state.repos.sessions._sessions  # 内存实现内部断言
    assert len(sessions) == 1
    stored = next(iter(sessions.values()))
    assert raw_access not in (stored.token_hash, stored.refresh_token_hash)
    assert len(stored.token_hash) == 64  # HMAC-SHA256 hex
