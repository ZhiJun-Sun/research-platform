"""FastAPI 应用入口。

启动：uv run --directory apps/api uvicorn hydrolab.main:app --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hydrolab import __version__
from hydrolab.api.container import build_repositories, build_services
from hydrolab.api.deps import (
    get_experiment_tracker,
    get_object_storage,
    get_run_executor,
    get_task_queue,
)
from hydrolab.api.routes import api_v1_router
from hydrolab.api.routes.dev_demo import router as dev_demo_router
from hydrolab.api.routes.health import router as health_router
from hydrolab.checkpoints.service import CheckpointService
from hydrolab.code_assets.directory_import import DirectoryImportService
from hydrolab.code_assets.imports import CodeImportService
from hydrolab.code_assets.services import TemplateEnvironmentService
from hydrolab.core.errors import register_error_handlers
from hydrolab.core.logging import configure_logging, get_logger, log_with
from hydrolab.core.middleware import RequestContextMiddleware
from hydrolab.core.rate_limit import FixedWindowRateLimiter
from hydrolab.core.settings import get_settings
from hydrolab.datasets.assets import AssetService
from hydrolab.datasets.imports import ImportService
from hydrolab.db.unit_of_work import UnitOfWork
from hydrolab.execution.collector import ArtifactCollector
from hydrolab.execution.publisher import OutboxPublisher
from hydrolab.execution.scheduler import GpuFifoScheduler
from hydrolab.execution.service import RunControlService
from hydrolab.experiments.service import ExperimentService
from hydrolab.results.service import ResultService

_DEV_BOOTSTRAP_EMAIL = "admin@hydrolab.cn"
_DEV_BOOTSTRAP_PASSWORD = "admin123456"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.validate_production()

    # 数据库接入：database_backend=mysql 时创建 SQL 会话工厂并先执行迁移；
    # memory 时保持进程内仓储（无库开发/测试）。
    session_factory = None
    if settings.database_backend == "mysql":
        from hydrolab.db.migrate import run_migrations
        from hydrolab.db.session import dispose, make_session_factory

        run_migrations(settings)
        session_factory = make_session_factory(settings)

    repos = build_repositories(session_factory)
    services = build_services(settings, repos)
    app.state.repos = repos
    app.state.auth_service = services.auth
    app.state.grant_service = services.grants
    app.state.share_service = services.share
    app.state.access_policy = services.policy
    app.state.shared_rate_limiter = FixedWindowRateLimiter(limit=30, window_seconds=60)

    # 领域仓储（B2–B8）：按 database_backend 选择 InMemory 或 SQL 实现。
    from hydrolab.db.factory import build_domain_stores

    stores = build_domain_stores(settings, session_factory)
    app.state.folders = stores.folders
    app.state.datasets = stores.datasets
    app.state.dataset_versions = stores.dataset_versions
    app.state.import_jobs = stores.import_jobs
    app.state.field_mappings = stores.field_mappings
    app.state.artifacts = stores.artifacts
    app.state.code_repositories = stores.code_repositories
    app.state.code_versions = stores.code_versions
    app.state.templates = stores.templates
    app.state.template_versions = stores.template_versions
    app.state.environments = stores.environments
    app.state.environment_versions = stores.environment_versions
    app.state.parameter_presets = stores.parameter_presets
    app.state.experiment_drafts = stores.experiment_drafts
    app.state.experiments = stores.experiments
    app.state.experiment_versions = stores.experiment_versions
    app.state.runs = stores.runs
    app.state.run_stages = stores.run_stages
    app.state.outbox = stores.outbox
    app.state.results = stores.results
    app.state.result_metrics = stores.result_metrics
    app.state.result_artifacts = stores.result_artifacts
    app.state.plot_specs = stores.plot_specs
    app.state.export_manifests = stores.export_manifests
    app.state.checkpoints = stores.checkpoints
    app.state.gpu_leases = stores.gpu_leases
    app.state.executions = stores.executions
    app.state.run_events = stores.run_events
    app.state.run_logs = stores.run_logs
    app.state.resource_samples = stores.resource_samples
    storage = get_object_storage()
    app.state.asset_service = AssetService(
        app.state.folders, app.state.datasets, repos.grants, services.policy
    )
    app.state.import_service = ImportService(
        app.state.datasets,
        app.state.dataset_versions,
        app.state.import_jobs,
        app.state.field_mappings,
        app.state.artifacts,
        storage,
        services.policy,
    )

    # B3 代码、模板、运行环境（仓储已由 stores 装配）。
    app.state.code_import_service = CodeImportService(
        app.state.code_repositories,
        app.state.code_versions,
        repos.grants,
        storage,
        services.policy,
    )
    # 本地目录快照导入：把服务器上的真实工程目录固化为不可变 CodeVersion。
    app.state.directory_import_service = DirectoryImportService(
        app.state.code_versions,
        storage,
        services.policy,
        settings.code_import_roots,
    )
    app.state.template_environment_service = TemplateEnvironmentService(
        app.state.code_versions,
        app.state.templates,
        app.state.template_versions,
        app.state.environments,
        app.state.environment_versions,
        app.state.parameter_presets,
        repos.grants,
        services.policy,
    )

    # B4 Draft/Experiment/Run：这里仅写入 QUEUED 元数据和 Outbox，不发起训练。
    app.state.experiment_service = ExperimentService(
        app.state.experiment_drafts,
        app.state.experiments,
        app.state.experiment_versions,
        app.state.runs,
        app.state.run_stages,
        app.state.outbox,
        app.state.dataset_versions,
        app.state.code_versions,
        app.state.template_versions,
        app.state.environment_versions,
        repos.grants,
        services.policy,
        transaction_factory=(
            (lambda: UnitOfWork(session_factory)) if session_factory is not None else None
        ),
    )

    app.state.result_service = ResultService(
        app.state.results,
        app.state.result_metrics,
        app.state.result_artifacts,
        app.state.plot_specs,
        app.state.export_manifests,
        app.state.runs,
        app.state.experiment_versions,
        storage,
    )

    app.state.checkpoint_service = CheckpointService(
        app.state.checkpoints, app.state.runs, app.state.experiment_versions
    )

    # B5/B6：执行控制与观测（仓储已由 stores 装配）。fake 后端只推进状态机；subprocess 后端真实执行并采集产物。
    executor = get_run_executor()
    # 真实执行器把每行 stdout 回流到 Run 日志，前端可增量拉取。
    if hasattr(executor, "_log_sink"):
        async def _sink(run_id: object, line: str) -> None:
            await app.state.run_logs.append(run_id, line)

        executor._log_sink = _sink

    app.state.run_control_service = RunControlService(
        app.state.runs,
        app.state.outbox,
        app.state.gpu_leases,
        app.state.executions,
        app.state.run_events,
        app.state.run_logs,
        app.state.resource_samples,
        get_task_queue(),
        executor,
        tracker=get_experiment_tracker(),
        versions=app.state.experiment_versions,
        code_versions=app.state.code_versions,
        template_versions=app.state.template_versions,
        storage=storage,
        collector=ArtifactCollector(storage),
        # 数据集仓储：让 Run 选定的数据版本被真正物化进工作目录，
        # 而不是回落到全局 DATA_ROOT 软链接。
        dataset_versions=app.state.dataset_versions,
        artifacts=app.state.artifacts,
        result_service=app.state.result_service,
    )

    # 单机双卡 FIFO 调度只对真实 Runner 启用。Fake 后端保留显式 start/complete
    # 语义，既避免测试自动推进，也便于接口级状态机调试。
    if settings.run_executor_backend == "subprocess":
        app.state.gpu_scheduler = GpuFifoScheduler(app.state.runs, app.state.run_control_service)
        app.state.gpu_scheduler.start()
    else:
        app.state.gpu_scheduler = None

    app.state.outbox_publisher = None
    if settings.task_queue_backend == "celery":
        app.state.outbox_publisher = OutboxPublisher(app.state.run_control_service)

    # 首个管理员 bootstrap：仅系统无用户时执行一次
    email = settings.bootstrap_admin_email
    password = settings.bootstrap_admin_password
    if settings.environment in ("local", "test") and (email is None or password is None):
        email = email or _DEV_BOOTSTRAP_EMAIL
        password = password or _DEV_BOOTSTRAP_PASSWORD
    if email and password:
        created = await services.auth.bootstrap_admin(
            email, password, settings.bootstrap_admin_name
        )
        if created is not None:
            log_with(
                get_logger("hydrolab.bootstrap"),
                30,
                "admin_bootstrapped",
                email=created.email,
                hint="首个管理员已创建；local 默认值仅用于开发，生产必须显式配置",
            )

    log_with(
        get_logger("hydrolab.bootstrap"),
        20,
        "application_started",
        environment=settings.environment,
        object_storage_backend=settings.object_storage_backend,
        task_queue_backend=settings.task_queue_backend,
        experiment_tracker_backend=settings.experiment_tracker_backend,
        run_executor_backend=settings.run_executor_backend,
    )
    try:
        if app.state.outbox_publisher is not None:
            app.state.outbox_publisher.start()
        yield
    finally:
        if app.state.outbox_publisher is not None:
            await app.state.outbox_publisher.stop()
        if app.state.gpu_scheduler is not None:
            await app.state.gpu_scheduler.stop()
        if settings.database_backend == "mysql":
            from hydrolab.db.session import dispose

            await dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    app = FastAPI(
        title="HydroLab API",
        version=__version__,
        description="水文时序实验平台后端。业务契约见 plans/02，Adapter 准入见 plans/05。",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(api_v1_router)
    if settings.environment != "production":
        app.include_router(dev_demo_router, prefix="/api/v1")
    return app


app = create_app()
