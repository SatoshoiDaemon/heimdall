import redis.asyncio as redis
from src.core.config import config
import logging

log = logging.getLogger("modbot.redis")

class RedisClient:
    redis_conn: redis.Redis = None

    @classmethod
    async def connect(cls):
        log.info("Connecting to Redis...")
        cls.redis_conn = await redis.from_url(config.REDIS_URI, decode_responses=True)
        await cls.redis_conn.ping()
        log.info("Redis connected successfully.")

    @classmethod
    async def close(cls):
        if cls.redis_conn:
            await cls.redis_conn.close()
            log.info("Redis connection closed.")
