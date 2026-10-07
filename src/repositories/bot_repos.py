from src.repositories.base import BaseRepository
from src.models.domain import GuildConfig, Warn, Note, Punishment
from typing import Optional, List

class ConfigRepository(BaseRepository):
    def __init__(self):
        super().__init__("configs")

    async def get_config(self, guild_id: int) -> Optional[GuildConfig]:
        doc = await self.find_one({"guild_id": guild_id})
        if doc:
            return GuildConfig(**doc)
        return None

    async def upsert_config(self, guild_id: int, updates: dict):
        await self.update_one({"guild_id": guild_id}, {"$set": updates}, upsert=True)

class WarnRepository(BaseRepository):
    def __init__(self):
        super().__init__("warns")

    async def get_user_warns(self, guild_id: int, user_id: int) -> List[Warn]:
        docs = await self.find_many({"guild_id": guild_id, "user_id": user_id})
        return [Warn(**d) for d in docs]

class NoteRepository(BaseRepository):
    def __init__(self):
        super().__init__("notes")

    async def get_user_notes(self, guild_id: int, user_id: int) -> List[Note]:
        docs = await self.find_many({"guild_id": guild_id, "user_id": user_id})
        return [Note(**d) for d in docs]

class PunishmentRepository(BaseRepository):
    def __init__(self):
        super().__init__("punishments")

    async def get_active_punishment(self, guild_id: int, user_id: int, p_type: str) -> Optional[Punishment]:
        doc = await self.find_one({"guild_id": guild_id, "user_id": user_id, "type": p_type, "active": True})
        if doc:
            return Punishment(**doc)
        return None

    async def mark_inactive(self, guild_id: int, user_id: int, p_type: str):
        await self.update_one(
            {"guild_id": guild_id, "user_id": user_id, "type": p_type, "active": True},
            {"$set": {"active": False}}
        )

class RBACRepository(BaseRepository):
    def __init__(self):
        super().__init__("rbac")

    async def get_role_permissions(self, guild_id: int, role_id: int) -> list[str]:
        doc = await self.find_one({"guild_id": guild_id, "role_id": role_id, "type": "role"})
        return doc.get("allowed_commands", []) if doc else []

    async def get_user_permissions(self, guild_id: int, user_id: int) -> list[str]:
        doc = await self.find_one({"guild_id": guild_id, "user_id": user_id, "type": "user"})
        return doc.get("allowed_commands", []) if doc else []

    async def set_role_permissions(self, guild_id: int, role_id: int, allowed: list[str]):
        await self.update_one(
            {"guild_id": guild_id, "role_id": role_id, "type": "role"},
            {"$set": {"allowed_commands": allowed, "guild_id": guild_id, "role_id": role_id, "type": "role"}},
            upsert=True
        )

    async def set_user_permissions(self, guild_id: int, user_id: int, allowed: list[str]):
        await self.update_one(
            {"guild_id": guild_id, "user_id": user_id, "type": "user"},
            {"$set": {"allowed_commands": allowed, "guild_id": guild_id, "user_id": user_id, "type": "user"}},
            upsert=True
        )
