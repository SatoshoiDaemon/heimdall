import discord

from src.models.domain import GuildConfig
from src.repositories.bot_repos import ConfigRepository
from src.services.cache_service import CacheService
from src.services.lock_service import LockService

ACCESS_PERMISSIONS = discord.Permissions(
    view_channel=True,
    send_messages=True,
    send_messages_in_threads=True,
    read_message_history=True,
    add_reactions=True,
    embed_links=True,
    attach_files=True,
    external_emojis=True,
    external_stickers=True,
    connect=True,
    speak=True,
    stream=True,
    use_voice_activation=True,
    use_application_commands=True,
).value


class ConfigService:
    repo = ConfigRepository()

    @classmethod
    async def get_guild_config(cls, guild_id: int) -> GuildConfig:
        async with LockService.get_lock(f"config:{guild_id}"):
            key = f"config:{guild_id}"
            cached = await CacheService.get(key)
            if cached is not None:
                return GuildConfig(**cached)
            doc = await cls.repo.find_one({"guild_id": guild_id})
            if doc is None:
                await cls.repo.update_one(
                    {"guild_id": guild_id}, {"$setOnInsert": {"guild_id": guild_id}}, upsert=True
                )
                doc = await cls.repo.find_one({"guild_id": guild_id})
            obj = GuildConfig(**doc)
            await CacheService.set(key, obj.model_dump(by_alias=True), ttl=60)
            return obj

    @classmethod
    async def update_guild_config(cls, guild_id: int, updates: dict):
        from src.core.database import Database

        forbidden = {"id", "_id", "guild_id"}
        if forbidden.intersection(updates) or set(updates) - set(GuildConfig.model_fields):
            raise ValueError("Unknown or immutable configuration field.")
        async with LockService.get_lock(f"config:{guild_id}"):
            doc = await cls.repo.find_one({"guild_id": guild_id})
            current = doc or {"_id": "new", "guild_id": guild_id}
            validated = GuildConfig(**{**current, **updates})
            updates = {key: validated.model_dump()[key] for key in updates}
            await cls.repo.update_one({"guild_id": guild_id}, {"$set": updates}, upsert=True)
            await CacheService.invalidate_guild_config(guild_id)
            Database.after_commit(lambda: CacheService._entries.pop(f"config:{guild_id}", None))
