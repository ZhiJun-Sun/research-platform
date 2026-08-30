"""B2 数据闭环测试：文件夹、导入、映射确认与版本冻结。"""


from tests.conftest import TestContext, login


async def _dataset(ctx: TestContext) -> tuple[dict[str, str], str]:
    headers = await login(ctx, "admin@hydrolab.cn", "admin123456")
    resp = await ctx.client.post("/api/v1/datasets", json={"name": "北江流域"}, headers=headers)
    assert resp.status_code == 201, resp.text
    return headers, resp.json()["id"]


async def test_folder_create_move_and_prevent_cycle(ctx: TestContext) -> None:
    headers = await login(ctx, "admin@hydrolab.cn", "admin123456")
    root = await ctx.client.post("/api/v1/folders", json={"name": "研究数据"}, headers=headers)
    child = await ctx.client.post(
        "/api/v1/folders", json={"name": "北江", "parent_id": root.json()["id"]}, headers=headers
    )
    assert child.status_code == 201
    resp = await ctx.client.patch(
        f"/api/v1/folders/{root.json()['id']}",
        json={"parent_id": child.json()["id"]},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_dataset_import_mapping_freezes_immutable_version(ctx: TestContext) -> None:
    headers, dataset_id = await _dataset(ctx)
    resp = await ctx.client.post(
        "/api/v1/dataset-imports",
        json={"dataset_id": dataset_id, "source_type": "UPLOAD"},
        headers=headers,
    )
    assert resp.status_code == 201
    job_id = resp.json()["id"]
    csv = "date,streamflow,precipitation,basin_id\n2020-01-01,1.2,5.1,BJ01\n"
    resp = await ctx.client.post(
        f"/api/v1/dataset-imports/{job_id}/fake-upload",
        json={"filename": "north-river.csv", "content": csv},
        headers=headers,
    )
    assert resp.json()["status"] == "MAPPING_REQUIRED"

    mapping = await ctx.client.get(f"/api/v1/dataset-imports/{job_id}/mapping", headers=headers)
    items = mapping.json()["items"]
    resp = await ctx.client.post(
        f"/api/v1/dataset-imports/{job_id}/confirm-mapping", json={"items": items}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    version = resp.json()
    assert version["version_no"] == 1
    assert version["status"] == "READY"
    assert version["content_hash"]
    assert version["manifest"]["format"] == "CSV"

    versions = await ctx.client.get(f"/api/v1/datasets/{dataset_id}/versions", headers=headers)
    assert versions.status_code == 200
    assert len(versions.json()) == 1


async def test_mapping_requires_exactly_one_time_field(ctx: TestContext) -> None:
    headers, dataset_id = await _dataset(ctx)
    job = await ctx.client.post(
        "/api/v1/dataset-imports",
        json={"dataset_id": dataset_id, "source_type": "UPLOAD"}, headers=headers
    )
    job_id = job.json()["id"]
    await ctx.client.post(
        f"/api/v1/dataset-imports/{job_id}/fake-upload",
        json={"filename": "x.csv", "content": "date,flow\n2020-01-01,1\n"}, headers=headers
    )
    resp = await ctx.client.post(
        f"/api/v1/dataset-imports/{job_id}/confirm-mapping",
        json={"items": [{"source_name": "date", "semantic": "FEATURE"}]}, headers=headers
    )
    assert resp.status_code == 422


async def test_import_idempotency_cancel_retry(ctx: TestContext) -> None:
    headers, dataset_id = await _dataset(ctx)
    payload = {"dataset_id": dataset_id, "source_type": "UPLOAD"}
    headers_with_key = {**headers, "Idempotency-Key": "import-1"}
    first = await ctx.client.post("/api/v1/dataset-imports", json=payload, headers=headers_with_key)
    second = await ctx.client.post("/api/v1/dataset-imports", json=payload, headers=headers_with_key)
    assert first.json()["id"] == second.json()["id"]
    job_id = first.json()["id"]
    cancelled = await ctx.client.post(f"/api/v1/dataset-imports/{job_id}/cancel", headers=headers)
    assert cancelled.json()["status"] == "CANCELLED"
    retried = await ctx.client.post(f"/api/v1/dataset-imports/{job_id}/retry", headers=headers)
    assert retried.status_code == 201
    assert retried.json()["status"] == "UPLOADING"


async def test_dataset_owner_isolation(ctx: TestContext, admin_headers: dict[str, str]) -> None:
    _owner_headers, dataset_id = await _dataset(ctx)
    invitation = await ctx.client.post(
        "/api/v1/admin/invitations", json={"email": "data-other@hydrolab.cn"}, headers=admin_headers
    )
    accepted = await ctx.client.post(
        f"/api/v1/invitations/{invitation.json()['token']}/accept",
        json={"display_name": "other", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {accepted.json()['tokens']['access_token']}"}
    resp = await ctx.client.get(f"/api/v1/datasets/{dataset_id}", headers=other_headers)
    assert resp.status_code == 403
