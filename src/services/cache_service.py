"""Bounded process-local TTL cache. Values never escape by reference."""

import copy
from collections import OrderedDict
from time import monotonic
from typing import Any


class CacheService:
    MAX_ENTRIES = 4096
    _entries: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()

    @classmethod
    def cleanup(cls):
        now = monotonic()
        for key, (expires, _) in list(cls._entries.items()):
            if expires <= now:
                cls._entries.pop(key, None)

    @classmethod
    async def get(cls, key: str) -> dict[str, Any] | None:
        entry = cls._entries.get(key)
        if entry is None:
            return None
        expires, value = entry
        if expires <= monotonic():
            cls._entries.pop(key, None)
            return None
        cls._entries.move_to_end(key)
        return copy.deepcopy(value)

    @classmethod
    async def set(cls, key: str, data: dict, ttl: int = 60):
        if ttl <= 0:
            cls._entries.pop(key, None)
            return
        cls._entries[key] = (monotonic() + ttl, copy.deepcopy(data))
        cls._entries.move_to_end(key)
        while len(cls._entries) > cls.MAX_ENTRIES:
            cls._entries.popitem(last=False)

    @classmethod
    async def delete(cls, key: str):
        cls._entries.pop(key, None)

    @classmethod
    def evict_prefix(cls, prefix: str):
        for key in list(cls._entries):
            if key.startswith(prefix):
                cls._entries.pop(key, None)

    @classmethod
    async def invalidate_guild_config(cls, guild_id: int):
        cls._entries.pop(f"config:{guild_id}", None)

    @classmethod
    async def invalidate_rbac(cls, guild_id: int):
        cls.evict_prefix(f"rbac:{guild_id}:")

    @classmethod
    def clear(cls):
        cls._entries.clear()
