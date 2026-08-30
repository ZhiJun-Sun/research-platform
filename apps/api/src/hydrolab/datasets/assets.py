"""文件夹与数据集应用服务。"""

from uuid import UUID

from hydrolab.access.policy import AccessPolicy
from hydrolab.core.errors import conflict, not_found, validation_error
from hydrolab.datasets.entities import AssetFolder, Dataset
from hydrolab.datasets.repositories import DatasetRepository, FolderRepository
from hydrolab.domain.entities import ResourceGrant, User, utcnow
from hydrolab.domain.enums import ResourceType, Role
from hydrolab.repositories import GrantRepository


class AssetService:
    def __init__(
        self,
        folders: FolderRepository,
        datasets: DatasetRepository,
        grants: GrantRepository,
        policy: AccessPolicy,
    ) -> None:
        self._folders = folders
        self._datasets = datasets
        self._grants = grants
        self._policy = policy

    async def create_folder(self, owner: User, name: str, parent_id: UUID | None) -> AssetFolder:
        name = name.strip()
        if not name or "/" in name:
            raise validation_error("文件夹名称不能为空且不能包含 /")
        if parent_id:
            parent = await self._folders.get(parent_id)
            if parent is None:
                raise not_found("父文件夹不存在")
            if parent.owner_id != owner.id:
                raise not_found("父文件夹不存在")
            path_key = f"{parent.path_key}/{name}"
        else:
            path_key = name
        siblings = await self._folders.list_by_owner(owner.id)
        if any(folder.parent_id == parent_id and folder.name == name for folder in siblings):
            raise conflict("同级文件夹名称已存在")
        folder = AssetFolder(owner_id=owner.id, parent_id=parent_id, name=name, path_key=path_key)
        return await self._folders.add(folder)

    async def move_folder(self, owner: User, folder_id: UUID, new_parent_id: UUID | None) -> AssetFolder:
        folder = await self._folders.get(folder_id)
        if folder is None or folder.owner_id != owner.id:
            raise not_found("文件夹不存在")
        if new_parent_id == folder_id:
            raise validation_error("文件夹不能移动到自身")
        parent: AssetFolder | None = None
        if new_parent_id:
            parent = await self._folders.get(new_parent_id)
            if parent is None or parent.owner_id != owner.id:
                raise not_found("目标文件夹不存在")
            # 不能移动进自己的子树
            if parent.path_key == folder.path_key or parent.path_key.startswith(folder.path_key + "/"):
                raise validation_error("不能移动到自身的子文件夹")
        all_folders = await self._folders.list_by_owner(owner.id)
        if any(
            item.id != folder.id and item.parent_id == new_parent_id and item.name == folder.name
            for item in all_folders
        ):
            raise conflict("目标目录已存在同名文件夹")
        old_prefix = folder.path_key
        new_prefix = f"{parent.path_key}/{folder.name}" if parent else folder.name
        folder.parent_id, folder.path_key, folder.updated_at = new_parent_id, new_prefix, utcnow()
        await self._folders.update(folder)
        # 同步修正所有子节点 path_key
        for item in all_folders:
            if item.id != folder.id and item.path_key.startswith(old_prefix + "/"):
                item.path_key = new_prefix + item.path_key[len(old_prefix) :]
                item.updated_at = utcnow()
                await self._folders.update(item)
        return folder

    async def list_folders(self, owner: User) -> list[AssetFolder]:
        return sorted(await self._folders.list_by_owner(owner.id), key=lambda folder: folder.path_key)

    async def create_dataset(
        self, owner: User, name: str, folder_id: UUID | None, description: str = ""
    ) -> Dataset:
        name = name.strip()
        if not name:
            raise validation_error("数据集名称不能为空")
        if folder_id:
            folder = await self._folders.get(folder_id)
            if folder is None or folder.owner_id != owner.id:
                raise not_found("文件夹不存在")
        dataset = Dataset(owner_id=owner.id, folder_id=folder_id, name=name, description=description)
        await self._datasets.add(dataset)
        await self._grants.add(
            ResourceGrant(
                resource_type=ResourceType.DATASET,
                resource_id=dataset.id,
                subject_id=owner.id,
                role=Role.OWNER,
                granted_by=owner.id,
            )
        )
        return dataset

    async def get_dataset(self, actor: User, dataset_id: UUID) -> Dataset:
        dataset = await self._datasets.get(dataset_id)
        if dataset is None:
            raise not_found("数据集不存在")
        await self._policy.require(actor, ResourceType.DATASET, dataset_id, Role.VIEWER)
        return dataset

    async def list_datasets(
        self, actor: User, q: str | None = None, folder_id: UUID | None = None
    ) -> list[Dataset]:
        # B2 内存基线：只返回 owner 自己的资源；B1 授权资源在 SQL 查询期扩展为 grant join。
        items = await self._datasets.list_by_owner(actor.id)
        if q:
            lowered = q.lower()
            items = [item for item in items if lowered in item.name.lower()]
        if folder_id is not None:
            items = [item for item in items if item.folder_id == folder_id]
        return sorted(items, key=lambda item: (item.created_at, item.id.hex), reverse=True)
