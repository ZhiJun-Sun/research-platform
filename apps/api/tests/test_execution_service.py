"""RunControlService 受控 argv 渲染（Agent B · 训练输出契约）单测。"""

import types
from uuid import uuid4

from hydrolab.execution.service import RunControlService


def _svc(requires_image_digest: bool) -> RunControlService:
    svc = object.__new__(RunControlService)
    svc._executor = types.SimpleNamespace(requires_image_digest=requires_image_digest)
    svc._experiment_name = lambda run: run.experiment_name
    return svc


def _run() -> types.SimpleNamespace:
    return types.SimpleNamespace(id=uuid4(), experiment_name="北江迁移")


def test_render_argv_injects_output_dir_for_subprocess() -> None:
    svc = _svc(requires_image_digest=False)
    run = _run()
    argv = ["python", "train.py", "--output", "{OUTPUT_DIR}", "--run", "{run_id}", "--name", "{experiment}"]
    rendered = svc._render_argv(argv, {}, run, "/tmp/hydrolab/output")
    assert rendered[rendered.index("--output") + 1] == "/tmp/hydrolab/output"
    assert rendered[rendered.index("--run") + 1] == str(run.id)
    assert rendered[rendered.index("--name") + 1] == "北江迁移"


def test_render_argv_injects_container_output_dir_for_docker() -> None:
    svc = _svc(requires_image_digest=True)
    run = _run()
    argv = ["python", "train.py", "--output", "{OUTPUT_DIR}"]
    rendered = svc._render_argv(argv, {}, run, "/workspace/output")
    assert rendered[rendered.index("--output") + 1] == "/workspace/output"


def test_process_output_dir_depends_on_executor_type() -> None:
    assert _svc(False)._process_output_dir("/tmp/ws") == "/tmp/ws/output"
    assert _svc(True)._process_output_dir("/tmp/ws") == "/workspace/output"
