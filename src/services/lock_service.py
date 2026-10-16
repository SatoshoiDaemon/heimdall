"""Per-resource asyncio locks for one Heimdall process, including its shards."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from src.core.exceptions import ModBotException


@dataclass
class _Resource:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class LockService:
    MAX_RESOURCES = 4096
    _resources: dict[str, _Resource] = {}

    @classmethod
    @asynccontextmanager
    async def get_lock(cls, resource_key: str, timeout: float = 10):
        resource = cls._resources.get(resource_key)
        if resource is None:
            if len(cls._resources) >= cls.MAX_RESOURCES:
                raise ModBotException("Too many operations in progress. Retry shortly.")
            resource = cls._resources[resource_key] = _Resource()
        resource.users += 1
        acquired = False
        try:
            try:
                await asyncio.wait_for(resource.lock.acquire(), timeout=timeout)
            except TimeoutError as error:
                raise ModBotException("This resource is busy. Retry shortly.") from error
            acquired = True
            yield
        finally:
            if acquired:
                resource.lock.release()
            resource.users -= 1
            if resource.users == 0:
                cls._resources.pop(resource_key, None)
