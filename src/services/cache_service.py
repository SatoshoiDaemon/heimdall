import json
import logging
from typing import Any

from redis.exceptions import RedisError

from src.core.redis_client import RedisClient

log = logging.getLogger("modbot.cache")


class CacheService:
    @staticmethod
    async def get(key: str) -> dict[str, Any] | None:
        conn = RedisClient.redis_conn
        try:
            data = await conn.get(key)
        except RedisError:
            log.warning("Cache unavailable; reading authoritative database")
            return None
        if data:
            return json.loads(data)
        return None

    @staticmethod
    async def set(key: str, data: dict, ttl: int = 3600):
        conn = RedisClient.redis_conn
        try:
            await conn.set(key, json.dumps(data), ex=ttl)
        except RedisError:
            log.warning("Cache write skipped")

    @staticmethod
    async def delete(key: str):
        conn = RedisClient.redis_conn
        await conn.delete(key)

    @staticmethod
    async def invalidate_guild_config(guild_id: int):
        await CacheService.delete(f"config:{guild_id}")

    @staticmethod
    async def invalidate_rbac(guild_id: int):
        # We might want to flush all user/role RBACs for this guild or individual
        # For simplicity, we invalidate by pattern or expect rigorous keys
        conn = RedisClient.redis_conn
        batch = []
        async for key in conn.scan_iter(match=f"rbac:{guild_id}:*", count=100):
            batch.append(key)
            if len(batch) == 100:
                await conn.delete(*batch)
                batch.clear()
        if batch:
            await conn.delete(*batch)
