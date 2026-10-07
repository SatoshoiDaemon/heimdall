from src.repositories.bot_repos import RBACRepository
from src.services.cache_service import CacheService

class RBACService:
    repo = RBACRepository()

    @classmethod
    async def has_permission(cls, guild_id: int, user_id: int, role_ids: list[int], command_name: str) -> bool:
        # Check user permission first
        u_key = f"rbac:{guild_id}:u:{user_id}"
        cached_u = await CacheService.get(u_key)
        if cached_u is not None:
            user_perms = cached_u.get("allowed", [])
        else:
            user_perms = await cls.repo.get_user_permissions(guild_id, user_id)
            await CacheService.set(u_key, {"allowed": user_perms})
            
        if command_name in user_perms or "*" in user_perms:
            return True

        # Check role permissions securely
        for role_id in role_ids:
            r_key = f"rbac:{guild_id}:r:{role_id}"
            cached_r = await CacheService.get(r_key)
            if cached_r is not None:
                role_perms = cached_r.get("allowed", [])
            else:
                role_perms = await cls.repo.get_role_permissions(guild_id, role_id)
                await CacheService.set(r_key, {"allowed": role_perms})
                
            if command_name in role_perms or "*" in role_perms:
                return True

        return False

    @classmethod
    async def set_role_permission(cls, guild_id: int, role_id: int, commands: list[str]):
        await cls.repo.set_role_permissions(guild_id, role_id, commands)
        await CacheService.invalidate_rbac(guild_id)

    @classmethod
    async def set_user_permission(cls, guild_id: int, user_id: int, commands: list[str]):
        await cls.repo.set_user_permissions(guild_id, user_id, commands)
        await CacheService.invalidate_rbac(guild_id)
