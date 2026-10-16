import asyncio
import contextlib
import uuid

from redis.exceptions import RedisError

from src.core.exceptions import ModBotException
from src.core.redis_client import RedisClient


class LockService:
    @staticmethod
    @contextlib.asynccontextmanager
    async def get_lock(resource_key: str, timeout: int = 120):
        """Renewed lease. Losing Redis cancels the owner, never runs unlocked."""
        token = uuid.uuid4().hex
        conn = RedisClient.redis_conn
        try:
            acquired = await conn.set(resource_key, token, nx=True, ex=timeout)
        except RedisError as error:
            raise ModBotException("Redis is unavailable; retry this operation later.") from error
        if not acquired:
            raise ModBotException("This resource is busy. Retry shortly.")
        owner = asyncio.current_task()
        lost = False

        async def renew():
            nonlocal lost
            try:
                while True:
                    await asyncio.sleep(timeout / 3)
                    renewed = await conn.eval(
                        "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('expire',KEYS[1],ARGV[2]) else return 0 end",
                        1,
                        resource_key,
                        token,
                        timeout,
                    )
                    if not renewed:
                        raise ModBotException("Lock ownership lost")
            except asyncio.CancelledError:
                raise
            except Exception:
                lost = True
                owner.cancel()

        task = asyncio.create_task(renew())
        try:
            yield
        except asyncio.CancelledError:
            if lost:
                raise ModBotException(
                    "Lock lease lost; operation retained for reconciliation."
                ) from None
            raise
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            with contextlib.suppress(RedisError):
                await conn.eval(
                    "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",
                    1,
                    resource_key,
                    token,
                )
