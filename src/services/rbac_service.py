from src.repositories.bot_repos import RBACRepository


class RBACService:
    repo = RBACRepository()

    @classmethod
    async def has_permission(
        cls, guild_id: int, user_id: int, role_ids: list[int], command_name: str
    ) -> bool:
        user_perms = await cls.repo.get_user_permissions(guild_id, user_id)
        if command_name in user_perms or "*" in user_perms:
            return True
        # One DB query for every role rather than a round trip for each role.
        docs = await cls.repo.find_many(
            {"guild_id": guild_id, "type": "role", "role_id": {"$in": role_ids}}
        )
        return any(
            command_name in d.get("allowed_commands", []) or "*" in d.get("allowed_commands", [])
            for d in docs
        )

    @classmethod
    async def set_role_permission(cls, guild_id: int, role_id: int, commands: list[str]):
        await cls.repo.set_role_permissions(guild_id, role_id, commands)

    @classmethod
    async def set_user_permission(cls, guild_id: int, user_id: int, commands: list[str]):
        await cls.repo.set_user_permissions(guild_id, user_id, commands)
