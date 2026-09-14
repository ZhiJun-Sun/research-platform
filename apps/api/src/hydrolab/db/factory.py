"""按 Settings 组装全部领域仓储（B1–B8）。

database_backend=memory -> InMemory 实现（无库开发/测试）；
database_backend=mysql  -> SQL 实现（真实持久化，需先执行 Alembic 迁移）。
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hydrolab.core.settings import Settings

if TYPE_CHECKING:
    pass


@dataclass
class DomainStores:
    """与 main.py 中 app.state.* 对应的一组领域存储。"""

    # B2 数据集
    folders: object
    datasets: object
    dataset_versions: object
    import_jobs: object
    field_mappings: object
    artifacts: object
    # B3 代码/模板/环境
    code_repositories: object
    code_versions: object
    templates: object
    template_versions: object
    environments: object
    environment_versions: object
    parameter_presets: object
    # B4 实验
    experiment_drafts: object
    experiments: object
    experiment_versions: object
    runs: object
    run_stages: object
    outbox: object
    # B4 结果
    results: object
    result_metrics: object
    result_artifacts: object
    plot_specs: object
    export_manifests: object
    # B7 检查点
    checkpoints: object
    # B5/B6 执行与观测
    gpu_leases: object
    executions: object
    run_events: object
    run_logs: object
    resource_samples: object


def _build_memory() -> DomainStores:
    from hydrolab.checkpoints.memory import InMemoryCheckpoints
    from hydrolab.code_assets.memory import (
        InMemoryCodeRepositories,
        InMemoryCodeVersions,
        InMemoryEnvironments,
        InMemoryEnvironmentVersions,
        InMemoryPresets,
        InMemoryTemplates,
        InMemoryTemplateVersions,
    )
    from hydrolab.datasets.memory import (
        InMemoryArtifactRepository,
        InMemoryDatasetRepository,
        InMemoryDatasetVersionRepository,
        InMemoryFieldMappingRepository,
        InMemoryFolderRepository,
        InMemoryImportJobRepository,
    )
    from hydrolab.execution.memory import (
        InMemoryExecutions,
        InMemoryGpuLeases,
        InMemoryLogs,
        InMemoryResourceSamples,
        InMemoryRunEvents,
    )
    from hydrolab.experiments.memory import (
        InMemoryDrafts,
        InMemoryExperiments,
        InMemoryExperimentVersions,
        InMemoryOutbox,
        InMemoryRuns,
        InMemoryRunStages,
    )
    from hydrolab.results.memory import (
        InMemoryArtifacts,
        InMemoryExports,
        InMemoryMetrics,
        InMemoryPlots,
        InMemoryResults,
    )

    return DomainStores(
        folders=InMemoryFolderRepository(),
        datasets=InMemoryDatasetRepository(),
        dataset_versions=InMemoryDatasetVersionRepository(),
        import_jobs=InMemoryImportJobRepository(),
        field_mappings=InMemoryFieldMappingRepository(),
        artifacts=InMemoryArtifactRepository(),
        code_repositories=InMemoryCodeRepositories(),
        code_versions=InMemoryCodeVersions(),
        templates=InMemoryTemplates(),
        template_versions=InMemoryTemplateVersions(),
        environments=InMemoryEnvironments(),
        environment_versions=InMemoryEnvironmentVersions(),
        parameter_presets=InMemoryPresets(),
        experiment_drafts=InMemoryDrafts(),
        experiments=InMemoryExperiments(),
        experiment_versions=InMemoryExperimentVersions(),
        runs=InMemoryRuns(),
        run_stages=InMemoryRunStages(),
        outbox=InMemoryOutbox(),
        results=InMemoryResults(),
        result_metrics=InMemoryMetrics(),
        result_artifacts=InMemoryArtifacts(),
        plot_specs=InMemoryPlots(),
        export_manifests=InMemoryExports(),
        checkpoints=InMemoryCheckpoints(),
        gpu_leases=InMemoryGpuLeases(gpu_count=2),
        executions=InMemoryExecutions(),
        run_events=InMemoryRunEvents(),
        run_logs=InMemoryLogs(),
        resource_samples=InMemoryResourceSamples(),
    )


def build_domain_stores(settings: Settings = None, session_factory=None) -> DomainStores:
    if session_factory is not None:
        return _build_sql(session_factory)
    return _build_memory()


def _build_sql(session_factory) -> DomainStores:
    from hydrolab.db.repositories.checkpoints import SqlCheckpoints
    from hydrolab.db.repositories.code_assets import (
        SqlCodeRepositoryStore,
        SqlCodeVersionStore,
        SqlEnvironmentStore,
        SqlEnvironmentVersionStore,
        SqlPresetStore,
        SqlTemplateStore,
        SqlTemplateVersionStore,
    )
    from hydrolab.db.repositories.datasets import (
        SqlArtifactRepository,
        SqlDatasetRepository,
        SqlDatasetVersionRepository,
        SqlFieldMappingRepository,
        SqlFolderRepository,
        SqlImportJobRepository,
    )
    from hydrolab.db.repositories.execution import (
        SqlExecutions,
        SqlGpuLeases,
        SqlLogs,
        SqlResourceSamples,
        SqlRunEvents,
    )
    from hydrolab.db.repositories.experiments import (
        SqlDraftStore,
        SqlExperimentStore,
        SqlExperimentVersionStore,
        SqlOutboxStore,
        SqlRunStageStore,
        SqlRunStore,
    )
    from hydrolab.db.repositories.results import (
        SqlArtifacts,
        SqlExports,
        SqlMetrics,
        SqlPlots,
        SqlResults,
    )

    return DomainStores(
        folders=SqlFolderRepository(session_factory),
        datasets=SqlDatasetRepository(session_factory),
        dataset_versions=SqlDatasetVersionRepository(session_factory),
        import_jobs=SqlImportJobRepository(session_factory),
        field_mappings=SqlFieldMappingRepository(session_factory),
        artifacts=SqlArtifactRepository(session_factory),
        code_repositories=SqlCodeRepositoryStore(session_factory),
        code_versions=SqlCodeVersionStore(session_factory),
        templates=SqlTemplateStore(session_factory),
        template_versions=SqlTemplateVersionStore(session_factory),
        environments=SqlEnvironmentStore(session_factory),
        environment_versions=SqlEnvironmentVersionStore(session_factory),
        parameter_presets=SqlPresetStore(session_factory),
        experiment_drafts=SqlDraftStore(session_factory),
        experiments=SqlExperimentStore(session_factory),
        experiment_versions=SqlExperimentVersionStore(session_factory),
        runs=SqlRunStore(session_factory),
        run_stages=SqlRunStageStore(session_factory),
        outbox=SqlOutboxStore(session_factory),
        results=SqlResults(session_factory),
        result_metrics=SqlMetrics(session_factory),
        result_artifacts=SqlArtifacts(session_factory),
        plot_specs=SqlPlots(session_factory),
        export_manifests=SqlExports(session_factory),
        checkpoints=SqlCheckpoints(session_factory),
        gpu_leases=SqlGpuLeases(session_factory, gpu_count=2),
        executions=SqlExecutions(session_factory),
        run_events=SqlRunEvents(session_factory),
        run_logs=SqlLogs(session_factory),
        resource_samples=SqlResourceSamples(session_factory),
    )