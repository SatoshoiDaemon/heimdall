from datetime import UTC, datetime
from typing import Any

from src.core.database import Database
from src.models.domain import Case, GuildConfig, Note, Punishment, Warn
from src.repositories.base import BaseRepository


class ConfigRepository(BaseRepository):
    def __init__(self):
        super().__init__("configs")

    async def get_config(self, guild_id: int) -> GuildConfig | None:
        doc = await self.find_one({"guild_id": guild_id})
        if doc:
            return GuildConfig(**doc)
        return None

    async def upsert_config(self, guild_id: int, updates: dict):
        await self.update_one({"guild_id": guild_id}, {"$set": updates}, upsert=True)


class WarnRepository(BaseRepository):
    def __init__(self):
        super().__init__("warns")

    async def get_user_warns(
        self, guild_id: int, user_id: int, page: int = 1, page_size: int = 5
    ) -> list[Warn]:
        docs = await self.find_page({"guild_id": guild_id, "user_id": user_id}, page, page_size)
        return [Warn(**d) for d in docs]

    async def get_by_case_number(self, guild_id: int, case_number: int) -> Warn | None:
        doc = await self.find_one({"guild_id": guild_id, "case_number": case_number})
        return Warn(**doc) if doc else None

    async def revoke(self, guild_id: int, case_number: int) -> int:
        return await self.update_one(
            {"guild_id": guild_id, "case_number": case_number, "revoked": {"$ne": True}},
            {"$set": {"revoked": True}},
        )


class NoteRepository(BaseRepository):
    def __init__(self):
        super().__init__("notes")

    async def get_user_notes(
        self, guild_id: int, user_id: int, page: int = 1, page_size: int = 5
    ) -> list[Note]:
        docs = await self.find_page({"guild_id": guild_id, "user_id": user_id}, page, page_size)
        return [Note(**d) for d in docs]


class PunishmentRepository(BaseRepository):
    def __init__(self):
        super().__init__("punishments")

    async def get_active_punishment(
        self, guild_id: int, user_id: int, p_type: str
    ) -> Punishment | None:
        doc = await self.find_one(
            {"guild_id": guild_id, "user_id": user_id, "type": p_type, "active": True}
        )
        if doc:
            return Punishment(**doc)
        return None

    async def mark_inactive(self, guild_id: int, user_id: int, p_type: str):
        await self.update_one(
            {"guild_id": guild_id, "user_id": user_id, "type": p_type, "active": True},
            {"$set": {"active": False}},
        )

    async def mark_inactive_by_case(self, guild_id: int, case_number: int) -> int:
        return await self.update_one(
            {"guild_id": guild_id, "case_number": case_number, "active": True},
            {"$set": {"active": False}},
        )


class CaseRepository(BaseRepository):
    def __init__(self):
        super().__init__("cases")

    async def create_case(
        self,
        *,
        guild_id: int,
        action: str,
        target_user_id: int | None,
        moderator_id: int,
        reason: str,
        duration_seconds: int | None = None,
        channel_id: int | None = None,
        amount: int | None = None,
        related_case_number: int | None = None,
        command_source: str | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = "completed",
        origin: str = "manual",
        operation_id: str | None = None,
    ) -> Case:
        case_number = await Database.next_case_number(guild_id)
        document = {
            "case_number": case_number,
            "guild_id": guild_id,
            "action": action,
            "target_user_id": target_user_id,
            "moderator_id": moderator_id,
            "reason": reason,
            "duration_seconds": duration_seconds,
            "channel_id": channel_id,
            "amount": amount,
            "created_at": datetime.now(UTC),
            "active": status == "completed" and action in {"WARN", "BAN", "TIMEOUT"},
            "revoked": False,
            "related_case_number": related_case_number,
            "command_source": command_source,
            "metadata": metadata or {},
            "status": status,
            "origin": origin,
            "operation_id": operation_id,
        }
        case_id = await self.insert_one(document)
        document["_id"] = case_id
        return Case(**document)

    async def get_case(self, guild_id: int, case_number: int) -> Case | None:
        document = await self.find_one({"guild_id": guild_id, "case_number": case_number})
        return Case(**document) if document else None

    async def get_latest_active(
        self, guild_id: int, target_user_id: int, action: str
    ) -> Case | None:
        document = await self.col.find_one(
            {
                "guild_id": guild_id,
                "target_user_id": target_user_id,
                "action": action,
                "revoked": False,
                "active": True,
                "status": "completed",
            },
            sort=[("case_number", -1)],
        )
        return Case(**document) if document else None

    async def list_cases(
        self,
        guild_id: int,
        *,
        target_user_id: int | None = None,
        page: int = 1,
        page_size: int = 5,
        moderator_id: int | None = None,
        action: str | None = None,
        origin: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Case]:
        query: dict[str, Any] = {"guild_id": guild_id}
        if target_user_id is not None:
            query["target_user_id"] = target_user_id
        if not 1 <= page_size <= 100 or page < 1:
            raise ValueError("Invalid pagination.")
        for key, value in (("moderator_id", moderator_id), ("action", action), ("origin", origin)):
            if value is not None:
                query[key] = value
        if since or until:
            query["created_at"] = {}
            if since:
                query["created_at"]["$gte"] = since
            if until:
                query["created_at"]["$lte"] = until
        cursor = (
            self.col.find(query)
            .sort("case_number", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return [Case(**document) for document in await cursor.to_list(length=page_size)]

    async def revoke(self, guild_id: int, case_number: int) -> int:
        return await self.update_one(
            {"guild_id": guild_id, "case_number": case_number, "revoked": False},
            {"$set": {"revoked": True, "active": False}},
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
            {
                "$set": {
                    "allowed_commands": allowed,
                    "guild_id": guild_id,
                    "role_id": role_id,
                    "type": "role",
                }
            },
            upsert=True,
        )

    async def set_user_permissions(self, guild_id: int, user_id: int, allowed: list[str]):
        await self.update_one(
            {"guild_id": guild_id, "user_id": user_id, "type": "user"},
            {
                "$set": {
                    "allowed_commands": allowed,
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "type": "user",
                }
            },
            upsert=True,
        )
