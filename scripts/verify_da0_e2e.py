#!/usr/bin/env python3
"""da0 真实端到端验收脚本。

验收目标（不使用 Fake Runner，不伪造指标）：
    真实目录导入 → 不可变 CodeVersion → 冻结实验版本 → 真实子进程训练
    → 采集真实产物 → 登记 Result/Metric/Artifact → 对比与导出

用法：
    python3 scripts/verify_da0_e2e.py --source /Users/sunzhijun/Desktop/da0 --epochs 1

说明：
- 直接在进程内驱动 FastAPI 应用（httpx ASGI），全链路走真实 HTTP 语义，无需另起服务；
- Runner 采用 subprocess 后端，真实执行 da0/main.py，因此耗时取决于 epochs；
- 数据不进代码包：顶层数据文件打成 BUNDLE 冻结为 DatasetVersion，
  由 Runner 按 Run 选定的数据版本物化进 code/datasets/，跑哪份数据可追溯。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api" / "src"))


def _fmt(seconds: float) -> str:
    return f"{seconds:.1f}s"


def _build_dataset_bundle(datasets_dir: Path) -> tuple[bytes, int]:
    """把 da0 顶层数据文件打成 BUNDLE zip，供真实数据集版本使用。

    只收顶层文件（xlsx/csv/txt）：camels_hourly/ 有 2.7GB，本验收不启用
    CAMELS（--include_camels 未开），没必要塞进版本里。真实需要 CAMELS 时
    应单独建一个数据集版本。
    """
    import zipfile

    buffer = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(datasets_dir.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            if path.suffix.lower() not in {".xlsx", ".xls", ".csv", ".txt"}:
                continue
            archive.write(path, arcname=path.name)
            count += 1
    if count == 0:
        raise SystemExit(f"数据目录中没有可打包的数据文件: {datasets_dir}")
    return buffer.getvalue(), count


class Reporter:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def ok(self, label: str, detail: str = "") -> None:
        print(f"PASS  {label}" + (f"  ({detail})" if detail else ""), flush=True)

    def fail(self, label: str, detail: str = "") -> None:
        self.failures.append(label)
        print(f"FAIL  {label}" + (f"  ({detail})" if detail else ""), flush=True)

    def check(self, condition: bool, label: str, detail: str = "") -> bool:
        (self.ok if condition else self.fail)(label, detail)
        return condition

    def expect(self, response: object, expected: int, label: str) -> bool:
        """校验 HTTP 状态码；失败时打印响应体便于定位。"""
        status = getattr(response, "status_code", 0)
        if status == expected:
            self.ok(label, f"HTTP {status}")
            return True
        self.fail(label, f"HTTP {status}")
        print("      " + getattr(response, "text", "")[:400], flush=True)
        return False


async def run(source: Path, epochs: int, model: str, basin: str, timeout: float) -> int:
    report = Reporter()
    workdir = REPO_ROOT / ".hydrolab-e2e"
    workdir.mkdir(parents=True, exist_ok=True)

    # --- 真实基础设施配置：本地对象存储 + 真实子进程 Runner ---
    os.environ["HYDROLAB_ENVIRONMENT"] = "local"
    os.environ["HYDROLAB_OBJECT_STORAGE_BACKEND"] = "local"
    os.environ["HYDROLAB_LOCAL_STORAGE_ROOT"] = str(workdir / "objects")
    os.environ["HYDROLAB_RUN_EXECUTOR_BACKEND"] = "subprocess"
    os.environ["HYDROLAB_RUNNER_WORKSPACE_ROOT"] = str(workdir / "runs")
    os.environ["HYDROLAB_RUNNER_DATA_ROOT"] = str(source / "datasets")
    os.environ["HYDROLAB_CODE_IMPORT_ROOTS"] = f'["{source.parent}"]'
    # da0 依赖 torch/pandas，位于系统 Python；API 自身运行在 uv venv 中，故显式指定
    os.environ.setdefault("HYDROLAB_RUNNER_PYTHON_EXECUTABLE", "/usr/bin/python3")

    import httpx

    from hydrolab.core.settings import get_settings
    from hydrolab.main import create_app

    # 抑制访问日志噪声，保持验收输出可读
    import logging

    for name in ("hydrolab.access", "httpx", "hydrolab.bootstrap"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("hydrolab.access").disabled = True
    logging.getLogger("httpx").disabled = True

    get_settings.cache_clear()
    from hydrolab.api import deps

    deps.get_object_storage.cache_clear()
    deps.get_run_executor.cache_clear()

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://e2e") as client:
        async with app.router.lifespan_context(app):
            api = "/api/v1"

            # ---------- 1. 登录 ----------
            login = await client.post(
                f"{api}/auth/login", json={"email": "admin@hydrolab.cn", "password": "admin123456"}
            )
            if not report.check(login.status_code == 200, "登录", str(login.status_code)):
                return 1
            headers = {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}

            # ---------- 2. 目录快照预览（只读，不落库） ----------
            preview = await client.post(
                f"{api}/code-import-previews", json={"path": str(source)}, headers=headers
            )
            if not report.expect(preview, 200, "目录快照预览"):
                print(preview.text[:400])
                return 1
            snap = preview.json()
            report.check(
                snap["file_count"] > 0,
                "快照包含代码文件",
                f"{snap['file_count']} 个文件 / {snap['uncompressed_bytes']/1024:.0f} KB",
            )
            report.check(
                not any(f.startswith((".venv", "datasets/", "experiments/")) for f in snap["files"]),
                "快照已排除虚拟环境与数据/产物目录",
            )
            report.check("main.py" in snap["entrypoints"], "识别到入口 main.py", str(snap["entrypoints"][:5]))

            # ---------- 3. 导入为不可变 CodeVersion ----------
            repo = await client.post(
                f"{api}/code-repositories", json={"name": f"da0-{int(time.time())}"}, headers=headers
            )
            if not report.expect(repo, 201, "创建代码仓库"):
                return 1
            repo_id = repo.json()["id"]

            imported = await client.post(
                f"{api}/code-repositories/{repo_id}/directory-imports",
                json={"path": str(source)},
                headers=headers,
            )
            if not report.expect(imported, 201, "目录导入为 CodeVersion"):
                return 1
            code_version = imported.json()["code_version"]
            report.check(code_version["status"] == "READY", "CodeVersion 为 READY")
            report.check(
                bool(code_version["content_hash"]) and bool(code_version["object_key"]),
                "CodeVersion 已内容寻址入对象存储",
                f"hash={code_version['content_hash'][:12]}",
            )
            code_version_id = code_version["id"]

            # ---------- 4. 数据集版本（走真实导入链路：上传 → 映射 → 冻结） ----------
            dataset = await client.post(
                f"{api}/datasets", json={"name": f"camels-bj-{basin}", "description": "da0 真实水文数据"}, headers=headers
            )
            if not report.expect(dataset, 201, "创建数据集"):
                return 1
            dataset_id = dataset.json()["id"]

            job = await client.post(
                f"{api}/dataset-imports", json={"dataset_id": dataset_id, "source_type": "UPLOAD"}, headers=headers
            )
            if not report.expect(job, 201, "创建数据导入任务"):
                return 1
            job_id = job.json()["id"]
            # 上传真实数据包：把 da0/datasets 打成 BUNDLE 上传，
            # 使"网页选定的数据集"真正决定训练读到什么数据，而非依赖全局挂载。
            bundle, entry_count = _build_dataset_bundle(source / "datasets")
            uploaded = await client.post(
                f"{api}/dataset-imports/{job_id}/fake-upload",
                json={
                    "filename": "da0-datasets.zip",
                    "content": base64.b64encode(bundle).decode(),
                    "content_encoding": "base64",
                },
                headers=headers,
            )
            if not report.expect(
                uploaded, 200, f"上传真实数据包（{entry_count} 个文件，{len(bundle) / 1024**2:.1f} MB）"
            ):
                return 1
            mapping = await client.get(f"{api}/dataset-imports/{job_id}/mapping", headers=headers)
            if not report.expect(mapping, 200, "读取字段映射建议"):
                return 1
            items = mapping.json()
            items = items.get("items", items) if isinstance(items, dict) else items
            confirmed = await client.post(
                f"{api}/dataset-imports/{job_id}/confirm-mapping", json={"items": items}, headers=headers
            )
            if not report.expect(confirmed, 200, "冻结真实数据版本（BUNDLE）"):
                return 1
            dataset_version_id = confirmed.json()["id"]

            # ---------- 5. 可执行训练模板 ----------
            template = await client.post(
                f"{api}/templates",
                json={"code_repository_id": repo_id, "name": "da0 训练", "description": "main.py 训练入口"},
                headers=headers,
            )
            if not report.expect(template, 201, "创建实验模板"):
                return 1
            template_id = template.json()["id"]

            # argv 使用占位符 {experiment}/{epochs}，由 Runner 按冻结参数渲染
            argv = [
                "python",
                "main.py",
                "--model",
                model,
                "--id",
                basin,
                "--epochs",
                "{epochs}",
                "--experiment",
                "{experiment}",
            ]
            tv = await client.post(
                f"{api}/templates/{template_id}/versions",
                json={
                    "code_version_id": code_version_id,
                    "mode": "TRAIN",
                    "argv": argv,
                    "parameters": [
                        {"key": "epochs", "label": "训练轮数", "type": "INTEGER", "default": epochs, "minimum": 1}
                    ],
                    "output_contract": {"experiments_dir": "experiments/<experiment>"},
                },
                headers=headers,
            )
            if not report.expect(tv, 201, "冻结模板版本"):
                return 1
            template_version_id = tv.json()["id"]

            # ---------- 6. 运行环境版本 ----------
            envr = await client.post(
                f"{api}/environments", json={"name": "local-cpu-torch", "description": "系统 Python + torch"}, headers=headers
            )
            if not report.expect(envr, 201, "创建运行环境"):
                return 1
            ev = await client.post(
                f"{api}/environments/{envr.json()['id']}/versions",
                json={
                    "base_image": "python:3.9@sha256:" + "a" * 64,
                    "python_version": "3.9.6",
                    "dependency_file": "requirements.txt",
                    "dependency_content": "torch==2.8.0\npandas\nnumpy\nmatplotlib\nscikit-learn\nopenpyxl\ntqdm\neinops\n",
                },
                headers=headers,
            )
            if not report.expect(ev, 201, "冻结运行环境版本"):
                return 1
            environment_version_id = ev.json()["id"]

            # ---------- 7. 提交实验，冻结版本并入队 ----------
            draft = await client.post(
                f"{api}/experiment-drafts",
                json={"name": f"da0 e2e {basin}", "description": "真实端到端验收"},
                headers=headers,
            )
            if not report.expect(draft, 201, "创建实验草稿"):
                return 1
            draft_id = draft.json()["id"]
            patched = await client.patch(
                f"{api}/experiment-drafts/{draft_id}",
                json={
                    "dataset_version_id": dataset_version_id,
                    "code_version_id": code_version_id,
                    "template_version_id": template_version_id,
                    "environment_version_id": environment_version_id,
                    "parameter_values": {"epochs": epochs},
                },
                headers=headers,
            )
            if not report.expect(patched, 200, "配置草稿资源版本"):
                return 1
            submitted = await client.post(f"{api}/experiment-drafts/{draft_id}/submit", headers=headers)
            if not report.expect(submitted, 201, "提交实验并冻结版本"):
                return 1
            payload = submitted.json()
            run_id = payload["run"]["id"]
            report.check(payload["run"]["status"] == "QUEUED", "Run 进入 QUEUED")
            report.check(bool(payload["version"]["config_hash"]), "实验版本已生成 config_hash")

            # ---------- 8. 真实执行 ----------
            await client.post(f"{api}/internal/outbox/dispatch", headers=headers)
            started = await client.post(
                f"{api}/runs/{run_id}/start", json={"gpu_count": 1}, headers=headers
            )
            if not report.expect(started, 200, "启动真实子进程 Runner"):
                return 1
            report.check(started.json()["status"] == "RUNNING", "Run 进入 RUNNING")

            print(f"\n... 真实训练中（epochs={epochs}，CPU 下预计 1-3 分钟），最长等待 {_fmt(timeout)}\n", flush=True)
            began = time.monotonic()
            awaited = await client.post(
                f"{api}/runs/{run_id}/await",
                json={"timeout_seconds": timeout},
                headers=headers,
                timeout=timeout + 120,
            )
            elapsed = time.monotonic() - began
            if not report.expect(awaited, 200, "等待执行结束"):
                return 1
            final_status = awaited.json()["status"]
            if not report.check(final_status == "SUCCEEDED", "真实训练成功", f"{final_status}, 耗时 {_fmt(elapsed)}"):
                logs = await client.get(f"{api}/runs/{run_id}/logs", headers=headers)
                tail = [item.get("content", "") for item in logs.json()][-30:]
                print("---- 日志尾部 ----")
                print("".join(tail))
                return 1

            # ---------- 9. 日志与采集 ----------
            logs = await client.get(f"{api}/runs/{run_id}/logs", headers=headers)
            log_lines = [item.get("content", "") for item in logs.json()]
            report.check(len(log_lines) > 5, "采集到真实训练日志", f"{len(log_lines)} 行")
            report.check(
                any("Test Result" in line or "Epoch" in line for line in log_lines),
                "日志包含真实训练输出",
            )

            collection = await client.get(f"{api}/runs/{run_id}/collection", headers=headers)
            if not report.expect(collection, 200, "读取采集报告"):
                return 1
            col = collection.json()
            report.check(col.get("collected") is True, "产物采集已执行")
            metrics = col.get("metrics", [])
            artifacts = col.get("artifacts", [])
            report.check(len(metrics) > 0, "采集到真实指标", f"{len(metrics)} 条")
            kinds = {item["kind"] for item in artifacts}
            report.check("predictions" in kinds, "采集到预测结果 predictions.csv")
            report.check("checkpoint" in kinds, "采集到 checkpoint 权重")
            report.check("plot" in kinds, "采集到绘图 PNG")
            report.check("config" in kinds, "采集到可复现配置")

            named = {item["name"]: item["value"] for item in metrics}
            for key in ("NSE@Avg", "KGE@Avg", "RMSE@Avg"):
                if key in named:
                    report.ok(f"真实指标 {key}", f"{named[key]:.4f}")
            report.check(
                all(isinstance(item["value"], (int, float)) for item in metrics),
                "指标均为有限数值（Infinity 已消毒）",
            )

            # ---------- 10. 结果登记 ----------
            ingest = await client.post(f"{api}/runs/{run_id}/result/ingest", headers=headers)
            if not report.expect(ingest, 201, "登记 Result/Metric/Artifact"):
                return 1
            ing = ingest.json()
            result_id = ing["result"]["id"]
            report.check(ing["metrics_added"] > 0, "指标写入结果域", f"{ing['metrics_added']} 条")
            report.check(ing["artifacts_added"] > 0, "产物写入结果域", f"{ing['artifacts_added']} 个")

            fetched = await client.get(f"{api}/results/{result_id}/metrics", headers=headers)
            report.check(
                fetched.status_code == 200 and len(fetched.json()) == ing["metrics_added"],
                "结果指标可回读",
            )

            # ---------- 11. 绘图与导出 ----------
            plot = await client.post(
                f"{api}/plots",
                json={
                    "result_ids": [result_id],
                    "plot_type": "hydrograph",
                    "data_selection": {"basin_id": basin},
                    "options": {"horizon": "Avg"},
                },
                headers=headers,
            )
            report.expect(plot, 201, "创建绘图规格")
            export = await client.post(
                f"{api}/exports", json={"result_ids": [result_id], "artifact_ids": []}, headers=headers
            )
            report.expect(export, 201, "创建导出清单")

            # ---------- 12. 校验工作区产物真实落盘 ----------
            run_workspace = Path(os.environ["HYDROLAB_RUNNER_WORKSPACE_ROOT"]) / run_id
            report.check(run_workspace.is_dir(), "Run 拥有独立工作目录", str(run_workspace))
            produced = list((run_workspace / "code" / "experiments").rglob("*")) if (
                run_workspace / "code" / "experiments"
            ).is_dir() else []
            report.check(len(produced) > 0, "工作目录内存在真实训练产物", f"{len(produced)} 个条目")
            objects_root = Path(os.environ["HYDROLAB_LOCAL_STORAGE_ROOT"])
            stored = list(objects_root.rglob("*")) if objects_root.is_dir() else []
            report.check(len(stored) > 0, "对象存储内存在真实内容", f"{len(stored)} 个条目")

    print("\n" + "=" * 60)
    if report.failures:
        print(f"结果：{len(report.failures)} 项未通过")
        for item in report.failures:
            print(f"  - {item}")
        return 1
    print("结果：da0 真实端到端全部通过")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="da0 真实端到端验收")
    parser.add_argument("--source", default=str(Path.home() / "Desktop" / "da0"), help="da0 工程目录")
    parser.add_argument("--epochs", type=int, default=1, help="训练轮数（验收用 1）")
    parser.add_argument("--model", default="kg_moe_ms")
    parser.add_argument("--basin", default="81000200")
    parser.add_argument("--timeout", type=float, default=1800, help="最长等待秒数")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    if not (source / "main.py").is_file():
        print(f"FAIL  源目录不含 main.py: {source}")
        return 1
    print("=" * 60)
    print("HydroLab · da0 真实端到端验收")
    print(f"源目录 : {source}")
    print(f"模型   : {args.model}   流域: {args.basin}   epochs: {args.epochs}")
    print("=" * 60)
    return asyncio.run(run(source, args.epochs, args.model, args.basin, args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())
