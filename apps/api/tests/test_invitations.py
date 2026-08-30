"""B1 邀请流程测试：无公开注册、管理员邀请、过期/已用/撤销。"""

from datetime import timedelta

from tests.conftest import (
    TestContext,
    invite_and_accept,
)


async def test_create_invitation_requires_admin(ctx: TestContext) -> None:
    resp = await ctx.client.post("/api/v1/admin/invitations", json={"email": "a@b.c"})
    assert resp.status_code == 401


async def test_no_public_registration(ctx: TestContext) -> None:
    resp = await ctx.client.post(
        "/api/v1/invitations/not-a-real-token/accept",
        json={"display_name": "x", "password": "password123"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "INVITATION_INVALID"


async def test_full_invitation_flow(ctx: TestContext, admin_headers: dict[str, str]) -> None:
    headers = await invite_and_accept(ctx, admin_headers, "user1@hydrolab.cn")
    resp = await ctx.client.get("/api/v1/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "user1@hydrolab.cn"
    assert resp.json()["is_admin"] is False


async def test_invitation_token_returned_once_and_stored_hashed(
    ctx: TestContext, admin_headers: dict[str, str]
) -> None:
    resp = await ctx.client.post(
        "/api/v1/admin/invitations", json={"email": "hash@hydrolab.cn"}, headers=admin_headers
    )
    raw_token = resp.json()["token"]
    invitations = ctx.app.state.repos.invitations._invitations
    stored = next(iter(invitations.values()))
    assert stored.token_hash != raw_token
    assert len(stored.token_hash) == 64

    # 列表接口不回传 token
    resp = await ctx.client.get("/api/v1/admin/invitations", headers=admin_headers)
    assert resp.status_code == 200
    assert "token" not in resp.text


async def test_invitation_cannot_be_used_twice(
    ctx: TestContext, admin_headers: dict[str, str]
) -> None:
    resp = await ctx.client.post(
        "/api/v1/admin/invitations", json={"email": "twice@hydrolab.cn"}, headers=admin_headers
    )
    token = resp.json()["token"]
    body = {"display_name": "u", "password": "password123"}
    resp = await ctx.client.post(f"/api/v1/invitations/{token}/accept", json=body)
    assert resp.status_code == 201
    resp = await ctx.client.post(f"/api/v1/invitations/{token}/accept", json=body)
    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "INVITATION_INVALID"


async def test_expired_invitation_rejected(ctx: TestContext, admin_headers: dict[str, str]) -> None:
    resp = await ctx.client.post(
        "/api/v1/admin/invitations",
        json={"email": "expired@hydrolab.cn", "expires_in_hours": 1},
        headers=admin_headers,
    )
    token = resp.json()["token"]
    # 手动将邀请过期
    invitations = ctx.app.state.repos.invitations._invitations
    stored = next(iter(invitations.values()))
    stored.expires_at = stored.expires_at - timedelta(hours=2)

    resp = await ctx.client.post(
        f"/api/v1/invitations/{token}/accept",
        json={"display_name": "u", "password": "password123"},
    )
    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "INVITATION_EXPIRED"


async def test_revoked_invitation_rejected(ctx: TestContext, admin_headers: dict[str, str]) -> None:
    resp = await ctx.client.post(
        "/api/v1/admin/invitations", json={"email": "revoke@hydrolab.cn"}, headers=admin_headers
    )
    body = resp.json()
    resp = await ctx.client.post(
        f"/api/v1/admin/invitations/{body['invitation']['id']}/revoke", headers=admin_headers
    )
    assert resp.status_code == 200
    resp = await ctx.client.post(
        f"/api/v1/invitations/{body['token']}/accept",
        json={"display_name": "u", "password": "password123"},
    )
    assert resp.status_code == 410


async def test_invite_existing_user_conflicts(
    ctx: TestContext, admin_headers: dict[str, str]
) -> None:
    await invite_and_accept(ctx, admin_headers, "dup@hydrolab.cn")
    resp = await ctx.client.post(
        "/api/v1/admin/invitations", json={"email": "dup@hydrolab.cn"}, headers=admin_headers
    )
    assert resp.status_code == 409


async def test_weak_password_rejected(ctx: TestContext, admin_headers: dict[str, str]) -> None:
    resp = await ctx.client.post(
        "/api/v1/admin/invitations", json={"email": "weak@hydrolab.cn"}, headers=admin_headers
    )
    token = resp.json()["token"]
    resp = await ctx.client.post(
        f"/api/v1/invitations/{token}/accept", json={"display_name": "u", "password": "short"}
    )
    assert resp.status_code == 422
