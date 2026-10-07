import json
from typing import Optional, Dict, Any
from src.core.redis_client import RedisClient

class CacheService:
    @staticmethod
    async def get(key: str) -> Optional[Dict[str, Any]]:
        conn = RedisClient.redis_conn
        data = await conn.get(key)
        if data:
            return json.loads(data)
        return None

    @staticmethod
    async def set(key: str, data: dict, ttl: int = 3600):
        conn = RedisClient.redis_conn
        await conn.set(key, json.dumps(data), ex=ttl)

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
        keys = await conn.keys(f"rbac:{guild_id}:*")
        if keys:
            await conn.delete(*keys)
