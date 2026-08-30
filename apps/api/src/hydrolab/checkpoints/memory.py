"""B7 Checkpoint InMemory 存储。"""

from uuid import UUID

from hydrolab.checkpoints.entities import Checkpoint


class InMemoryCheckpoints:
    def __init__(self) -> None:
        self.items: dict[UUID, Checkpoint] = {}

    async def add(self, item: Checkpoint) -> Checkpoint:
        self.items[item.id] = item
        return item

    async def get(self, checkpoint_id: UUID) -> Checkpoint | None:
        return self.items.get(checkpoint_id)

    async def list_by_owner(self, owner_id: UUID) -> list[Checkpoint]:
        return [item for item in self.items.values() if item.owner_id == owner_id]
