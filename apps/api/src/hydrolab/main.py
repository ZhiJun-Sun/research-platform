"""FastAPI 应用入口。

启动：uv run --directory apps/api uvicorn hydrolab.main:app --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hydrolab import __version__
from hydrolab.api.container import build_repositories, build_services
from hydrolab.api.deps import get_object_storage
from hydrolab.api.routes import api_v1_router
from hydrolab.api.routes.health import router as health_router
from hydrolab.code_assets.imports import CodeImportService
from hydrolab.code_assets.memory import (
    InMemoryCodeRepositories,
    InMemoryCodeVersions,
    InMemoryEnvironments,
    InMemoryEnvironmentVersions,
    InMemoryPresets,
    InMemoryTemplates,
    InMemoryTemplateVersions,
)
from hydrolab.code_assets.services import TemplateEnvironmentService
from hydrolab.core.errors import register_error_handlers
from hydrolab.core.logging import configure_logging, get_logger, log_with
from hydrolab.core.middleware import RequestContextMiddleware
from hydrolab.core.rate_limit import FixedWindowRateLimiter
from hydrolab.core.settings import get_settings
from hydrolab.datasets.assets import AssetService
from hydrolab.datasets.imports import ImportService
from hydrolab.datasets.memory import (
    InMemoryArtifactRepository,
    InMemoryDatasetRepository,
    InMemoryDatasetVersionRepository,
    InMemoryFieldMappingRepository,
    InMemoryFolderRepository,
    InMemoryImportJobRepository,
)

_DEV_BOOTSTRAP_EMAIL = "admin@hydrolab.cn"
_DEV_BOOTSTRAP_PASSWORD = "admin123456"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.validate_production()

    repos = build_repositories()
    services = build_services(settings, repos)
    app.state.repos = repos
    app.state.auth_service = services.auth
    app.state.grant_service = services.grants
    app.state.share_service = services.share
    app.state.access_policy = services.policy
    app.state.shared_rate_limiter = FixedWindowRateLimiter(limit=30, window_seconds=60)

    # B2 数据存储：与 B1 一样采用 InMemory Repository；对象内容复用 Fake/Local ObjectStorage。
    app.state.folders = InMemoryFolderRepository()
    app.state.datasets = InMemoryDatasetRepository()
    app.state.dataset_versions = InMemoryDatasetVersionRepository()
    app.state.import_jobs = InMemoryImportJobRepository()
    app.state.field_mappings = InMemoryFieldMappingRepository()
    app.state.artifacts = InMemoryArtifactRepository()
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

    # B3 代码、模板、运行环境：同样保持进程内版本仓储，未来替换为 SQL 实现。
    app.state.code_repositories = InMemoryCodeRepositories()
    app.state.code_versions = InMemoryCodeVersions()
    app.state.templates = InMemoryTemplates()
    app.state.template_versions = InMemoryTemplateVersions()
    app.state.environments = InMemoryEnvironments()
    app.state.environment_versions = InMemoryEnvironmentVersions()
    app.state.parameter_presets = InMemoryPresets()
    app.state.code_import_service = CodeImportService(
        app.state.code_repositories,
        app.state.code_versions,
        repos.grants,
        storage,
        services.policy,
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
    yield


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
    return app


app = create_app()
