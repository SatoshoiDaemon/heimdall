import uuid
import contextlib
from src.core.redis_client import RedisClient
from src.core.exceptions import ModBotException

class LockService:
    @staticmethod
    @contextlib.asynccontextmanager
    async def get_lock(resource_key: str, timeout: int = 10):
        """
        Distributed lock using Redis SET NX.
        Used to prevent race conditions during /warn, /purge or /captcha.
        """
        token = str(uuid.uuid4())
        redis_conn = RedisClient.redis_conn
        
        # Try to acquire lock
        acquired = await redis_conn.set(resource_key, token, nx=True, ex=timeout)
        if not acquired:
            raise ModBotException(f"Resource {resource_key} is currently locked by another process.")
            
        try:
            yield
        finally:
            # Release lock using Lua script to ensure atomic verification and deletion
            script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            await redis_conn.eval(script, 1, resource_key, token)
