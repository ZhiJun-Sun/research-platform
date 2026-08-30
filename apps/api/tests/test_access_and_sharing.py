"""B1 资源授权与分享测试：越权隔离、角色、只读链接生命周期、幂等。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from hydrolab.domain.entities import ResourceGrant
from hydrolab.domain.enums import ResourceType, Role
from tests.conftest import TestContext, invite_and_accept, login

DATASET = ResourceType.DATASET.value


async def _seed_owner(ctx: TestContext, owner_headers: dict[str, str], resource_id) -> None:
    me = await ctx.client.get("/api/v1/me", headers=owner_headers)
    owner_id = me.json()["id"]
    await ctx.app.state.repos.grants.add(
        ResourceGrant(
            resource_type=ResourceType.DATASET,
            resource_id=resource_id,
            subject_id=owner_id,
            role=Role.OWNER,
            granted_by=owner_id,
        )
    )


async def test_user_cannot_access_others_resource(
    ctx: TestContext, admin_headers: dict[str, str]
) -> None:
    owner_headers = await invite_and_accept(ctx, admin_headers, "owner@hydrolab.cn")
    stranger_headers = await invite_and_accept(ctx, admin_headers, "stranger@hydrolab.cn")
    resource_id = uuid4()
    await _seed_owner(ctx, owner_headers, resource_id)

    # 非授权用户：查看授权列表被拒
    resp = await ctx.client.get(
        f"/api/v1/resources/{DATASET}/{resource_id}/grants", headers=stranger_headers
    )
    assert resp.status_code == 403

    # 非授权用户：创建分享被拒
    resp = await ctx.client.post(
        "/api/v1/share-links",
        json={"resource_type": DATASET, "resource_id": str(resource_id)},
        headers=stranger_headers,
    )
    assert resp.status_code == 403

    # 所有者可以
    resp = await ctx.client.get(
        f"/api/v1/resources/{DATASET}/{resource_id}/grants", headers=owner_headers
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_viewer_grant_allows_read_but_not_manage(
    ctx: TestContext, admin_headers: dict[str, str]
) -> None:
    owner_headers = await invite_and_accept(ctx, admin_headers, "o2@hydrolab.cn")
    viewer_headers = await invite_and_accept(ctx, admin_headers, "v2@hydrolab.cn")
    resource_id = uuid4()
    await _seed_owner(ctx, owner_headers, resource_id)

    resp = await ctx.client.post(
        f"/api/v1/resources/{DATASET}/{resource_id}/grants",
        json={"email": "v2@hydrolab.cn", "role": "VIEWER"},
        headers=owner_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "VIEWER"

    # viewer 创建分享仍被拒（需要 OWNER）
    resp = await ctx.client.post(
        "/api/v1/share-links",
        json={"resource_type": DATASET, "resource_id": str(resource_id)},
        headers=viewer_headers,
    )
    assert resp.status_code == 403

    # viewer 不能撤销授权
    grants = await ctx.client.get(
        f"/api/v1/resources/{DATASET}/{resource_id}/grants", headers=owner_headers
    )
    grant_id = grants.json()[1]["id"]
    resp = await ctx.client.delete(
        f"/api/v1/resources/{DATASET}/{resource_id}/grants/{grant_id}", headers=viewer_headers
    )
    assert resp.status_code == 403


async def test_share_link_full_lifecycle(ctx: TestContext, admin_headers: dict[str, str]) -> None:
    owner_headers = await invite_and_accept(ctx, admin_headers, "share@hydrolab.cn")
    resource_id = uuid4()
    version_id = uuid4()
    await _seed_owner(ctx, owner_headers, resource_id)

    resp = await ctx.client.post(
        "/api/v1/share-links",
        json={
            "resource_type": DATASET,
            "resource_id": str(resource_id),
            "resource_version_id": str(version_id),
            "allowed_artifact_kinds": ["preview"],
            "expires_in_hours": 24,
        },
        headers=owner_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    token = body["token"]
    link_id = body["share_link"]["id"]

    # 存储哈希，不明文
    stored = next(iter(ctx.app.state.repos.share_links._links.values()))
    assert stored.token_hash != token

    # 公开访问：字段白名单，版本锁定
    resp = await ctx.client.get(f"/api/v1/shared/{token}")
    assert resp.status_code == 200
    shared = resp.json()
    assert shared["resource_id"] == str(resource_id)
    assert shared["resource_version_id"] == str(version_id)
    assert shared["permissions"] == ["read"]
    assert "token_hash" not in resp.text
    assert "created_by" not in resp.text

    # 访问计数
    resp = await ctx.client.get("/api/v1/share-links", headers=owner_headers)
    assert resp.json()[0]["access_count"] == 1

    # 撤销（幂等），公开访问立即失效
    resp = await ctx.client.post(f"/api/v1/share-links/{link_id}/revoke", headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json()["revoked_at"] is not None
    resp = await ctx.client.post(f"/api/v1/share-links/{link_id}/revoke", headers=owner_headers)
    assert resp.status_code == 200
    resp = await ctx.client.get(f"/api/v1/shared/{token}")
    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "SHARE_LINK_REVOKED"


async def test_share_link_expired(ctx: TestContext, admin_headers: dict[str, str]) -> None:
    owner_headers = await invite_and_accept(ctx, admin_headers, "exp@hydrolab.cn")
    resource_id = uuid4()
    await _seed_owner(ctx, owner_headers, resource_id)
    resp = await ctx.client.post(
        "/api/v1/share-links",
        json={"resource_type": DATASET, "resource_id": str(resource_id)},
        headers=owner_headers,
    )
    token = resp.json()["token"]
    stored = next(iter(ctx.app.state.repos.share_links._links.values()))
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    resp = await ctx.client.get(f"/api/v1/shared/{token}")
    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "SHARE_LINK_EXPIRED"


async def test_share_create_idempotency_key(
    ctx: TestContext, admin_headers: dict[str, str]
) -> None:
    owner_headers = await invite_and_accept(ctx, admin_headers, "idem@hydrolab.cn")
    resource_id = uuid4()
    await _seed_owner(ctx, owner_headers, resource_id)
    payload = {"resource_type": DATASET, "resource_id": str(resource_id)}

    resp1 = await ctx.client.post(
        "/api/v1/share-links", json=payload, headers={**owner_headers, "Idempotency-Key": "k-1"}
    )
    resp2 = await ctx.client.post(
        "/api/v1/share-links", json=payload, headers={**owner_headers, "Idempotency-Key": "k-1"}
    )
    assert resp1.status_code == 201 and resp2.status_code == 201
    assert resp1.json()["share_link"]["id"] == resp2.json()["share_link"]["id"]
    assert resp2.json()["token"] is None  # 幂等命中不重复下发原文
    assert len(ctx.app.state.repos.share_links._links) == 1


async def test_shared_endpoint_rate_limited(ctx: TestContext) -> None:
    # 防枚举：同客户端同 token 前缀超过 30 次/分钟返回 429
    last = None
    for _ in range(31):
        last = await ctx.client.get("/api/v1/shared/enumeration-attempt")
    assert last is not None
    assert last.status_code == 429
    assert last.json()["error"]["code"] == "RATE_LIMITED"


async def test_audit_records_security_actions(
    ctx: TestContext, admin_headers: dict[str, str]
) -> None:
    await invite_and_accept(ctx, admin_headers, "audit@hydrolab.cn")
    await login(ctx, "audit@hydrolab.cn", "userpass123")
    entries = await ctx.app.state.repos.audit.list_recent(50)
    actions = [e.action for e in entries]
    assert "invitation.created" in actions
    assert "invitation.accepted" in actions
    assert "user.login" in actions
    # 审计不含凭证
    for entry in entries:
        assert "password" not in str(entry.details)
        assert "token" not in str(entry.details) or "token_hash" not in str(entry.details)
