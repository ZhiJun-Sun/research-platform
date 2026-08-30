"""B3 模板、环境与参数预设应用服务。"""

import hashlib
import json
from typing import Any
from uuid import UUID

from hydrolab.access.policy import AccessPolicy
from hydrolab.code_assets.entities import (
    EnvironmentVersion,
    ExperimentTemplate,
    ParameterDefinition,
    ParameterPreset,
    RuntimeEnvironment,
    TemplateVersion,
)
from hydrolab.code_assets.enums import CodeVersionStatus, EnvironmentStatus, ParameterType, TemplateMode
from hydrolab.code_assets.repositories import (
    CodeVersionStore,
    EnvironmentStore,
    EnvironmentVersionStore,
    PresetStore,
    TemplateStore,
    TemplateVersionStore,
)
from hydrolab.core.errors import conflict, not_found, validation_error
from hydrolab.domain.entities import ResourceGrant, User, utcnow
from hydrolab.domain.enums import ResourceType, Role
from hydrolab.repositories import GrantRepository


class TemplateEnvironmentService:
    def __init__(
        self,
        code_versions: CodeVersionStore,
        templates: TemplateStore,
        template_versions: TemplateVersionStore,
        environments: EnvironmentStore,
        environment_versions: EnvironmentVersionStore,
        presets: PresetStore,
        grants: GrantRepository,
        policy: AccessPolicy,
    ) -> None:
        self._code_versions, self._templates, self._template_versions = code_versions, templates, template_versions
        self._environments, self._environment_versions, self._presets = environments, environment_versions, presets
        self._grants, self._policy = grants, policy

    async def create_template(
        self, owner: User, code_repository_id: UUID, name: str, description: str = ""
    ) -> ExperimentTemplate:
        await self._policy.require(owner, ResourceType.CODE_REPOSITORY, code_repository_id, Role.VIEWER)
        if not name.strip():
            raise validation_error("模板名称不能为空")
        template = await self._templates.add(
            ExperimentTemplate(
                owner_id=owner.id, code_repository_id=code_repository_id, name=name.strip(), description=description
            )
        )
        await self._grants.add(
            ResourceGrant(
                resource_type=ResourceType.EXPERIMENT_TEMPLATE,
                resource_id=template.id,
                subject_id=owner.id,
                role=Role.OWNER,
                granted_by=owner.id,
            )
        )
        return template

    async def create_template_version(
        self,
        owner: User,
        template_id: UUID,
        code_version_id: UUID,
        mode: TemplateMode,
        argv: list[str],
        parameters: list[ParameterDefinition],
        input_contract: dict[str, Any],
        output_contract: dict[str, Any],
    ) -> TemplateVersion:
        template = await self._require_template_owner(owner, template_id)
        code_version = await self._code_versions.get(code_version_id)
        if code_version is None or code_version.status != CodeVersionStatus.READY:
            raise conflict("模板必须引用 READY 状态的代码版本")
        self._validate_argv(argv)
        self._validate_parameters(parameters)
        if code_version.repository_id != template.code_repository_id:
            raise validation_error("模板代码版本不属于关联代码仓库")
        version = TemplateVersion(
            template_id=template_id,
            version_no=await self._template_versions.next_version_no(template_id),
            code_version_id=code_version_id,
            mode=mode,
            argv=argv,
            parameters=parameters,
            input_contract=input_contract,
            output_contract=output_contract,
        )
        return await self._template_versions.add(version)

    async def create_environment(self, owner: User, name: str, description: str = "") -> RuntimeEnvironment:
        if not name.strip():
            raise validation_error("运行环境名称不能为空")
        environment = await self._environments.add(
            RuntimeEnvironment(owner_id=owner.id, name=name.strip(), description=description)
        )
        await self._grants.add(
            ResourceGrant(
                resource_type=ResourceType.RUNTIME_ENVIRONMENT,
                resource_id=environment.id,
                subject_id=owner.id,
                role=Role.OWNER,
                granted_by=owner.id,
            )
        )
        return environment

    async def create_environment_version(
        self,
        owner: User,
        environment_id: UUID,
        base_image: str,
        python_version: str,
        dependency_file: str | None,
        dependency_content: str | None,
    ) -> EnvironmentVersion:
        await self._policy.require(owner, ResourceType.RUNTIME_ENVIRONMENT, environment_id, Role.OWNER)
        if not base_image or "@" not in base_image:
            raise validation_error("基础镜像必须使用不可变 digest，例如 python:3.11@sha256:...")
        if not python_version.startswith("3."):
            raise validation_error("当前仅支持 Python 3.x 环境")
        source = json.dumps(
            {
                "base_image": base_image,
                "python_version": python_version,
                "dependency_file": dependency_file,
                "dependency_content": dependency_content,
            },
            sort_keys=True,
        )
        version = EnvironmentVersion(
            environment_id=environment_id,
            version_no=await self._environment_versions.next_version_no(environment_id),
            status=EnvironmentStatus.READY,
            base_image=base_image,
            python_version=python_version,
            dependency_file=dependency_file,
            dependency_content=dependency_content,
            content_hash=hashlib.sha256(source.encode()).hexdigest(),
            frozen_at=utcnow(),
        )
        return await self._environment_versions.add(version)

    async def create_preset(
        self, owner: User, template_version_id: UUID, name: str, values: dict[str, Any]
    ) -> ParameterPreset:
        version = await self._template_versions.get(template_version_id)
        if version is None:
            raise not_found("模板版本不存在")
        await self._require_template_owner(owner, version.template_id)
        self._validate_values(version.parameters, values)
        if not name.strip():
            raise validation_error("参数预设名称不能为空")
        return await self._presets.add(
            ParameterPreset(
                owner_id=owner.id, template_version_id=template_version_id, name=name.strip(), values=values
            )
        )

    async def _require_template_owner(self, user: User, template_id: UUID) -> ExperimentTemplate:
        template = await self._templates.get(template_id)
        if template is None or template.owner_id != user.id:
            raise not_found("实验模板不存在")
        return template

    @staticmethod
    def _validate_argv(argv: list[str]) -> None:
        if not argv or any(not part or "\x00" in part for part in argv):
            raise validation_error("argv 必须是非空参数数组")
        if any(";" in part or "&&" in part or "|" in part for part in argv):
            raise validation_error("模板命令不允许 Shell 控制符；请使用 argv 参数数组")

    @staticmethod
    def _validate_parameters(parameters: list[ParameterDefinition]) -> None:
        keys = [item.key for item in parameters]
        if len(keys) != len(set(keys)):
            raise validation_error("模板参数 key 不能重复")
        for item in parameters:
            if item.type == ParameterType.SELECT and not item.choices:
                raise validation_error("SELECT 参数必须提供 choices")
            if item.minimum is not None and item.maximum is not None and item.minimum > item.maximum:
                raise validation_error("参数 minimum 不能大于 maximum")

    @staticmethod
    def _validate_values(definitions: list[ParameterDefinition], values: dict[str, Any]) -> None:
        definition_by_key = {item.key: item for item in definitions}
        unknown = set(values) - set(definition_by_key)
        if unknown:
            raise validation_error("参数预设包含未知字段", {"keys": sorted(unknown)})
        missing = [
            item.key for item in definitions if item.required and item.key not in values and item.default is None
        ]
        if missing:
            raise validation_error("参数预设缺少必填字段", {"keys": missing})
        for key, value in values.items():
            definition = definition_by_key[key]
            if definition.type == ParameterType.INTEGER and (not isinstance(value, int) or isinstance(value, bool)):
                raise validation_error("参数类型不匹配", {"key": key})
            if definition.type == ParameterType.NUMBER and (
                not isinstance(value, (int, float)) or isinstance(value, bool)
            ):
                raise validation_error("参数类型不匹配", {"key": key})
            if definition.type == ParameterType.BOOLEAN and not isinstance(value, bool):
                raise validation_error("参数类型不匹配", {"key": key})
            if definition.type == ParameterType.STRING and not isinstance(value, str):
                raise validation_error("参数类型不匹配", {"key": key})
            if definition.type == ParameterType.SELECT and value not in definition.choices:
                raise validation_error("参数选项不合法", {"key": key})
            if definition.minimum is not None and value < definition.minimum:
                raise validation_error("参数小于最小值", {"key": key})
            if definition.maximum is not None and value > definition.maximum:
                raise validation_error("参数大于最大值", {"key": key})
