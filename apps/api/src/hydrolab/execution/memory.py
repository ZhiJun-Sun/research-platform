"""B5/B6 执行与观测 InMemory 存储。"""

from datetime import datetime
from uuid import UUID

from hydrolab.execution.entities import GpuLease, ResourceSample, RunEvent, RunExecution, RunLogChunk
from hydrolab.ports.dto import EventType


class InMemoryGpuLeases:
    def __init__(self, gpu_count: int = 2) -> None:
        self.gpu_count = gpu_count
        self.items: dict[int, GpuLease] = {}

    async def acquire(self, run_id: UUID, count: int, expires_at: datetime) -> list[GpuLease]:
        available = [index for index in range(self.gpu_count) if index not in self.items]
        if len(available) < count:
            return []
        leases = [GpuLease(gpu_index=index, run_id=run_id, expires_at=expires_at) for index in available[:count]]
        for lease in leases:
            self.items[lease.gpu_index] = lease
        return leases

    async def list_by_run(self, run_id: UUID) -> list[GpuLease]:
        return [lease for lease in self.items.values() if lease.run_id == run_id]

    async def heartbeat(self, run_id: UUID, expires_at: datetime) -> list[GpuLease]:
        leases = await self.list_by_run(run_id)
        for lease in leases:
            lease.heartbeat_at = datetime.now(lease.heartbeat_at.tzinfo)
            lease.expires_at = expires_at
        return leases

    async def release_run(self, run_id: UUID) -> None:
        for index in [index for index, lease in self.items.items() if lease.run_id == run_id]:
            del self.items[index]


class InMemoryExecutions:
    def __init__(self) -> None:
        self.items: dict[UUID, RunExecution] = {}

    async def add(self, item: RunExecution) -> RunExecution:
        self.items[item.run_id] = item
        return item

    async def get(self, run_id: UUID) -> RunExecution | None:
        return self.items.get(run_id)

    async def remove(self, run_id: UUID) -> None:
        self.items.pop(run_id, None)


class InMemoryRunEvents:
    def __init__(self) -> None:
        self.items: list[RunEvent] = []
        self._next_id = 1

    async def append(self, event_type: EventType, run_id: UUID, payload: dict[str, object]) -> RunEvent:
        event = RunEvent(id=self._next_id, event_type=event_type, run_id=run_id, payload=payload)
        self._next_id += 1
        self.items.append(event)
        return event

    async def list_after(self, run_id: UUID, after_id: int = 0) -> list[RunEvent]:
        return [x for x in self.items if x.run_id == run_id and x.id > after_id]


class InMemoryLogs:
    def __init__(self) -> None:
        self.items: list[RunLogChunk] = []
        self._next_id = 1

    async def append(self, run_id: UUID, content: str, stream: str = "stdout") -> RunLogChunk:
        item = RunLogChunk(id=self._next_id, run_id=run_id, content=content, stream=stream)
        self._next_id += 1
        self.items.append(item)
        return item

    async def list_after(self, run_id: UUID, after_id: int = 0) -> list[RunLogChunk]:
        return [x for x in self.items if x.run_id == run_id and x.id > after_id]


class InMemoryResourceSamples:
    def __init__(self) -> None:
        self.items: list[ResourceSample] = []

    async def add(self, item: ResourceSample) -> ResourceSample:
        self.items.append(item)
        return item

    async def list_by_run(self, run_id: UUID) -> list[ResourceSample]:
        return [x for x in self.items if x.run_id == run_id]
