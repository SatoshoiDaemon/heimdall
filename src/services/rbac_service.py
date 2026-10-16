from src.core.database import Database, _session
from src.repositories.bot_repos import RBACRepository
from src.services.cache_service import CacheService
from src.services.lock_service import LockService


class RBACService:
    repo = RBACRepository()

    @classmethod
    async def has_permission(
        cls, guild_id: int, user_id: int, role_ids: list[int], command_name: str
    ) -> bool:
        key = f"rbac:{guild_id}:{user_id}:{','.join(map(str, sorted(role_ids)))}"
        async with LockService.get_lock(f"rbac:cache:{guild_id}"):
            cached = await CacheService.get(key) if _session.get() is None else None
            if cached is not None:
                permissions = cached["allowed"]
            else:
                docs = await cls.repo.find_many(
                    {
                        "guild_id": guild_id,
                        "$or": [
                            {"type": "user", "user_id": user_id},
                            {"type": "role", "role_id": {"$in": role_ids}},
                        ],
                    }
                )
                permissions = sorted(
                    {command for doc in docs for command in doc.get("allowed_commands", [])}
                )
                if _session.get() is None:
                    await CacheService.set(key, {"allowed": permissions}, ttl=60)
            return command_name in permissions or "*" in permissions

    @classmethod
    async def set_role_permission(cls, guild_id: int, role_id: int, commands: list[str]):
        async with LockService.get_lock(f"rbac:cache:{guild_id}"):
            await cls.repo.set_role_permissions(guild_id, role_id, commands)
            await CacheService.invalidate_rbac(guild_id)
            Database.after_commit(lambda: CacheService.evict_prefix(f"rbac:{guild_id}:"))

    @classmethod
    async def set_user_permission(cls, guild_id: int, user_id: int, commands: list[str]):
        async with LockService.get_lock(f"rbac:cache:{guild_id}"):
            await cls.repo.set_user_permissions(guild_id, user_id, commands)
            await CacheService.invalidate_rbac(guild_id)
            Database.after_commit(lambda: CacheService.evict_prefix(f"rbac:{guild_id}:"))
