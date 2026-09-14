"""B3 代码、模板和环境资产 API 测试。"""

import base64
import io
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from tests.conftest import TestContext, login


def _zip_bytes(entries: dict[str, str], symlink: bool = False) -> str:
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            if symlink:
                info = ZipInfo(name)
                info.external_attr = 0o120777 << 16
                archive.writestr(info, content)
            else:
                archive.writestr(name, content)
    return base64.b64encode(stream.getvalue()).decode()


async def _code_version(ctx: TestContext) -> tuple[dict[str, str], dict[str, object]]:
    headers = await login(ctx, "admin@hydrolab.cn", "admin123456")
    repo = await ctx.client.post("/api/v1/code-repositories", json={"name": "Hydro LSTM"}, headers=headers)
    assert repo.status_code == 201, repo.text
    content = _zip_bytes({"train.py": "print('train')", "requirements.txt": "torch==2.0"})
    version = await ctx.client.post(
        f"/api/v1/code-repositories/{repo.json()['id']}/zip-imports",
        json={"filename": "model.zip", "content_base64": content},
        headers=headers,
    )
    assert version.status_code == 201, version.text
    return headers, {"repository": repo.json(), "version": version.json()}


async def test_zip_import_creates_frozen_code_version(ctx: TestContext) -> None:
    headers, assets = await _code_version(ctx)
    version = assets["version"]
    assert version["version_no"] == 1
    assert version["status"] == "READY"
    assert version["content_hash"]
    assert "requirements.txt" in version["manifest"]["detected_manifests"]
    versions = await ctx.client.get(
        f"/api/v1/code-repositories/{assets['repository']['id']}/versions", headers=headers
    )
    assert len(versions.json()) == 1


async def test_zip_rejects_traversal_and_symlink(ctx: TestContext) -> None:
    headers = await login(ctx, "admin@hydrolab.cn", "admin123456")
    repo = await ctx.client.post("/api/v1/code-repositories", json={"name": "Safe code"}, headers=headers)
    for payload in (
        _zip_bytes({"../escape.py": "bad"}),
        _zip_bytes({"model_link": "outside"}, symlink=True),
    ):
        response = await ctx.client.post(
            f"/api/v1/code-repositories/{repo.json()['id']}/zip-imports",
            json={"filename": "unsafe.zip", "content_base64": payload},
            headers=headers,
        )
        assert response.status_code == 422


async def test_template_and_preset_validate_argv_and_parameters(ctx: TestContext) -> None:
    headers, assets = await _code_version(ctx)
    template = await ctx.client.post(
        "/api/v1/templates",
        json={"code_repository_id": assets["repository"]["id"], "name": "LSTM train"},
        headers=headers,
    )
    assert template.status_code == 201
    body = {
        "code_version_id": assets["version"]["id"],
        "mode": "TRAIN",
        "argv": ["python", "train.py", "--epochs", "{epochs}"],
        "parameters": [
            {"key": "epochs", "label": "Epochs", "type": "INTEGER", "required": True, "minimum": 1},
            {"key": "lr", "label": "Learning rate", "type": "NUMBER", "default": 0.001},
        ],
    }
    version = await ctx.client.post(f"/api/v1/templates/{template.json()['id']}/versions", json=body, headers=headers)
    assert version.status_code == 201, version.text
    preset = await ctx.client.post(
        "/api/v1/parameter-presets",
        json={"template_version_id": version.json()["id"], "name": "default", "values": {"epochs": 20, "lr": 0.01}},
        headers=headers,
    )
    assert preset.status_code == 201
    bad = await ctx.client.post(
        f"/api/v1/templates/{template.json()['id']}/versions",
        json={**body, "argv": ["python train.py; rm -rf /"]},
        headers=headers,
    )
    assert bad.status_code == 422


async def test_environment_requires_immutable_image_digest(ctx: TestContext) -> None:
    headers = await login(ctx, "admin@hydrolab.cn", "admin123456")
    environment = await ctx.client.post("/api/v1/environments", json={"name": "Python 3.11"}, headers=headers)
    assert environment.status_code == 201
    invalid = await ctx.client.post(
        f"/api/v1/environments/{environment.json()['id']}/versions",
        json={"base_image": "python:3.11", "python_version": "3.11"},
        headers=headers,
    )
    assert invalid.status_code == 422
    placeholder = await ctx.client.post(
        f"/api/v1/environments/{environment.json()['id']}/versions",
        json={"base_image": "python:3.11@sha256:REPLACE_ME", "python_version": "3.11"},
        headers=headers,
    )
    assert placeholder.status_code == 422
    short_hash = await ctx.client.post(
        f"/api/v1/environments/{environment.json()['id']}/versions",
        json={"base_image": "python:3.11@sha256:abc123", "python_version": "3.11"},
        headers=headers,
    )
    assert short_hash.status_code == 422
    ready = await ctx.client.post(
        f"/api/v1/environments/{environment.json()['id']}/versions",
        json={
            "base_image": f"python:3.11@sha256:{'a' * 64}",
            "python_version": "3.11",
            "dependency_file": "requirements.txt",
            "dependency_content": "torch==2.0",
        },
        headers=headers,
    )
    assert ready.status_code == 201, ready.text
    assert ready.json()["status"] == "READY"
    assert ready.json()["image_digest"] == f"python:3.11@sha256:{'a' * 64}"
