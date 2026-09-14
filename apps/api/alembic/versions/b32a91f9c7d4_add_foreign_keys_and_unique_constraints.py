"""add foreign keys and unique constraints

Revision ID: b32a91f9c7d4
Revises: 4e409406eb80
Create Date: 2026-09-13 10:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = 'b32a91f9c7d4'
down_revision: str | Sequence[str] | None = 'c0a111a2f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # B1 身份/授权
    op.create_foreign_key('fk_invitations_inviter_id_users', 'invitations', 'users', ['inviter_id'], ['id'])
    op.create_foreign_key('fk_sessions_user_id_users', 'sessions', 'users', ['user_id'], ['id'])
    op.create_foreign_key('fk_resource_grants_granted_by_users', 'resource_grants', 'users', ['granted_by'], ['id'])
    op.create_foreign_key('fk_share_links_created_by_users', 'share_links', 'users', ['created_by'], ['id'])
    op.create_foreign_key('fk_audit_logs_actor_id_users', 'audit_logs', 'users', ['actor_id'], ['id'])

    # B2 数据
    op.create_foreign_key('fk_asset_folders_owner_id_users', 'asset_folders', 'users', ['owner_id'], ['id'])
    op.create_foreign_key(
        'fk_asset_folders_parent_id_asset_folders',
        'asset_folders',
        'asset_folders',
        ['parent_id'],
        ['id'],
    )
    op.create_foreign_key('fk_datasets_owner_id_users', 'datasets', 'users', ['owner_id'], ['id'])
    op.create_foreign_key('fk_datasets_folder_id_asset_folders', 'datasets', 'asset_folders', ['folder_id'], ['id'])
    op.create_foreign_key(
        'fk_dataset_versions_dataset_id_datasets',
        'dataset_versions',
        'datasets',
        ['dataset_id'],
        ['id'],
    )
    op.create_foreign_key(
        'fk_dataset_versions_parent_version_id_dataset_versions',
        'dataset_versions',
        'dataset_versions',
        ['parent_version_id'],
        ['id'],
    )
    op.create_foreign_key('fk_artifacts_owner_id_users', 'artifacts', 'users', ['owner_id'], ['id'])
    op.create_foreign_key(
        'fk_field_mappings_import_job_id_dataset_import_jobs',
        'field_mappings',
        'dataset_import_jobs',
        ['import_job_id'],
        ['id'],
    )
    op.create_foreign_key('fk_dataset_import_jobs_owner_id_users', 'dataset_import_jobs', 'users', ['owner_id'], ['id'])
    op.create_foreign_key(
        'fk_dataset_import_jobs_dataset_id_datasets',
        'dataset_import_jobs',
        'datasets',
        ['dataset_id'],
        ['id'],
    )

    # B3 代码/模板/环境
    op.create_foreign_key('fk_code_repositories_owner_id_users', 'code_repositories', 'users', ['owner_id'], ['id'])
    op.create_foreign_key(
        'fk_code_versions_repository_id_code_repositories',
        'code_versions',
        'code_repositories',
        ['repository_id'],
        ['id'],
    )
    op.create_foreign_key(
        'fk_experiment_templates_owner_id_users',
        'experiment_templates',
        'users',
        ['owner_id'],
        ['id'],
    )
    op.create_foreign_key(
        'fk_experiment_templates_code_repository_id_code_repositories',
        'experiment_templates',
        'code_repositories',
        ['code_repository_id'],
        ['id'],
    )
    op.create_foreign_key(
        'fk_template_versions_template_id_experiment_templates',
        'template_versions',
        'experiment_templates',
        ['template_id'],
        ['id'],
    )
    op.create_foreign_key(
        'fk_template_versions_code_version_id_code_versions',
        'template_versions',
        'code_versions',
        ['code_version_id'],
        ['id'],
    )
    op.create_foreign_key(
        'fk_runtime_environments_owner_id_users',
        'runtime_environments',
        'users',
        ['owner_id'],
        ['id'],
    )
    op.create_foreign_key(
        'fk_environment_versions_environment_id_runtime_environments',
        'environment_versions',
        'runtime_environments',
        ['environment_id'],
        ['id'],
    )
    op.create_foreign_key('fk_parameter_presets_owner_id_users', 'parameter_presets', 'users', ['owner_id'], ['id'])
    op.create_foreign_key(
        'fk_parameter_presets_template_version_id_template_versions',
        'parameter_presets',
        'template_versions',
        ['template_version_id'],
        ['id'],
    )

    # B4 实验 / Run
    op.create_foreign_key('fk_experiment_drafts_owner_id_users', 'experiment_drafts', 'users', ['owner_id'], ['id'])
    op.create_foreign_key('fk_experiments_owner_id_users', 'experiments', 'users', ['owner_id'], ['id'])
    op.create_foreign_key(
        'fk_experiment_versions_experiment_id_experiments',
        'experiment_versions',
        'experiments',
        ['experiment_id'],
        ['id'],
    )
    op.create_foreign_key('fk_runs_experiment_id_experiments', 'runs', 'experiments', ['experiment_id'], ['id'])
    op.create_foreign_key(
        'fk_runs_experiment_version_id_experiment_versions',
        'runs',
        'experiment_versions',
        ['experiment_version_id'],
        ['id'],
    )
    op.create_foreign_key('fk_runs_owner_id_users', 'runs', 'users', ['owner_id'], ['id'])
    op.create_foreign_key('fk_run_stages_run_id_runs', 'run_stages', 'runs', ['run_id'], ['id'])
    # B4 幂等提交：同一 owner 的同一幂等键只能有一个 Run（防御并发重复提交）。
    op.create_unique_constraint('uq_runs_owner_idempotency_key', 'runs', ['owner_id', 'idempotency_key'])

    # B5/B6 执行与观测
    op.create_foreign_key('fk_gpu_leases_run_id_runs', 'gpu_leases', 'runs', ['run_id'], ['id'])
    op.create_foreign_key('fk_run_executions_run_id_runs', 'run_executions', 'runs', ['run_id'], ['id'])
    op.create_foreign_key('fk_run_events_run_id_runs', 'run_events', 'runs', ['run_id'], ['id'])
    op.create_foreign_key('fk_run_logs_run_id_runs', 'run_logs', 'runs', ['run_id'], ['id'])
    op.create_foreign_key('fk_resource_samples_run_id_runs', 'resource_samples', 'runs', ['run_id'], ['id'])

    # B7 Checkpoint
    op.create_foreign_key('fk_checkpoints_owner_id_users', 'checkpoints', 'users', ['owner_id'], ['id'])
    op.create_foreign_key('fk_checkpoints_source_run_id_runs', 'checkpoints', 'runs', ['source_run_id'], ['id'])
    op.create_foreign_key(
        'fk_checkpoints_source_experiment_version_id_experiment_versions',
        'checkpoints',
        'experiment_versions',
        ['source_experiment_version_id'],
        ['id'],
    )

    # B8 结果
    op.create_foreign_key('fk_results_run_id_runs', 'results', 'runs', ['run_id'], ['id'])
    op.create_foreign_key('fk_results_owner_id_users', 'results', 'users', ['owner_id'], ['id'])
    op.create_foreign_key('fk_metric_points_result_id_results', 'metric_points', 'results', ['result_id'], ['id'])
    op.create_foreign_key('fk_result_artifacts_result_id_results', 'result_artifacts', 'results', ['result_id'], ['id'])
    op.create_foreign_key('fk_plot_specs_owner_id_users', 'plot_specs', 'users', ['owner_id'], ['id'])
    op.create_foreign_key('fk_export_manifests_owner_id_users', 'export_manifests', 'users', ['owner_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_export_manifests_owner_id_users', 'export_manifests', type_='foreignkey')
    op.drop_constraint('fk_plot_specs_owner_id_users', 'plot_specs', type_='foreignkey')
    op.drop_constraint('fk_result_artifacts_result_id_results', 'result_artifacts', type_='foreignkey')
    op.drop_constraint('fk_metric_points_result_id_results', 'metric_points', type_='foreignkey')
    op.drop_constraint('fk_results_owner_id_users', 'results', type_='foreignkey')
    op.drop_constraint('fk_results_run_id_runs', 'results', type_='foreignkey')
    op.drop_constraint(
        'fk_checkpoints_source_experiment_version_id_experiment_versions',
        'checkpoints',
        type_='foreignkey',
    )
    op.drop_constraint('fk_checkpoints_source_run_id_runs', 'checkpoints', type_='foreignkey')
    op.drop_constraint('fk_checkpoints_owner_id_users', 'checkpoints', type_='foreignkey')
    op.drop_constraint('fk_resource_samples_run_id_runs', 'resource_samples', type_='foreignkey')
    op.drop_constraint('fk_run_logs_run_id_runs', 'run_logs', type_='foreignkey')
    op.drop_constraint('fk_run_events_run_id_runs', 'run_events', type_='foreignkey')
    op.drop_constraint('fk_run_executions_run_id_runs', 'run_executions', type_='foreignkey')
    op.drop_constraint('fk_gpu_leases_run_id_runs', 'gpu_leases', type_='foreignkey')
    op.drop_constraint('uq_runs_owner_idempotency_key', 'runs', type_='unique')
    op.drop_constraint('fk_run_stages_run_id_runs', 'run_stages', type_='foreignkey')
    op.drop_constraint('fk_runs_owner_id_users', 'runs', type_='foreignkey')
    op.drop_constraint('fk_runs_experiment_version_id_experiment_versions', 'runs', type_='foreignkey')
    op.drop_constraint('fk_runs_experiment_id_experiments', 'runs', type_='foreignkey')
    op.drop_constraint('fk_experiment_versions_experiment_id_experiments', 'experiment_versions', type_='foreignkey')
    op.drop_constraint('fk_experiments_owner_id_users', 'experiments', type_='foreignkey')
    op.drop_constraint('fk_experiment_drafts_owner_id_users', 'experiment_drafts', type_='foreignkey')
    op.drop_constraint(
        'fk_parameter_presets_template_version_id_template_versions',
        'parameter_presets',
        type_='foreignkey',
    )
    op.drop_constraint('fk_parameter_presets_owner_id_users', 'parameter_presets', type_='foreignkey')
    op.drop_constraint(
        'fk_environment_versions_environment_id_runtime_environments',
        'environment_versions',
        type_='foreignkey',
    )
    op.drop_constraint('fk_runtime_environments_owner_id_users', 'runtime_environments', type_='foreignkey')
    op.drop_constraint('fk_template_versions_code_version_id_code_versions', 'template_versions', type_='foreignkey')
    op.drop_constraint('fk_template_versions_template_id_experiment_templates', 'template_versions', type_='foreignkey')
    op.drop_constraint(
        'fk_experiment_templates_code_repository_id_code_repositories',
        'experiment_templates',
        type_='foreignkey',
    )
    op.drop_constraint('fk_experiment_templates_owner_id_users', 'experiment_templates', type_='foreignkey')
    op.drop_constraint('fk_code_versions_repository_id_code_repositories', 'code_versions', type_='foreignkey')
    op.drop_constraint('fk_code_repositories_owner_id_users', 'code_repositories', type_='foreignkey')
    op.drop_constraint('fk_dataset_import_jobs_dataset_id_datasets', 'dataset_import_jobs', type_='foreignkey')
    op.drop_constraint('fk_dataset_import_jobs_owner_id_users', 'dataset_import_jobs', type_='foreignkey')
    op.drop_constraint(
        'fk_field_mappings_import_job_id_dataset_import_jobs',
        'field_mappings',
        type_='foreignkey',
    )
    op.drop_constraint('fk_artifacts_owner_id_users', 'artifacts', type_='foreignkey')
    op.drop_constraint(
        'fk_dataset_versions_parent_version_id_dataset_versions',
        'dataset_versions',
        type_='foreignkey',
    )
    op.drop_constraint('fk_dataset_versions_dataset_id_datasets', 'dataset_versions', type_='foreignkey')
    op.drop_constraint('fk_datasets_folder_id_asset_folders', 'datasets', type_='foreignkey')
    op.drop_constraint('fk_datasets_owner_id_users', 'datasets', type_='foreignkey')
    op.drop_constraint('fk_asset_folders_parent_id_asset_folders', 'asset_folders', type_='foreignkey')
    op.drop_constraint('fk_audit_logs_actor_id_users', 'audit_logs', type_='foreignkey')
    op.drop_constraint('fk_share_links_created_by_users', 'share_links', type_='foreignkey')
    op.drop_constraint('fk_resource_grants_granted_by_users', 'resource_grants', type_='foreignkey')
    op.drop_constraint('fk_sessions_user_id_users', 'sessions', type_='foreignkey')
    op.drop_constraint('fk_invitations_inviter_id_users', 'invitations', type_='foreignkey')