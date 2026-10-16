import discord

from src.models.domain import GuildConfig
from src.repositories.bot_repos import ConfigRepository
from src.services.cache_service import CacheService

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
        # Read a small authoritative revision before consulting Redis; a failed
        # invalidation can never expose stale security-related configuration.
        revision_doc = await cls.repo.find_one({"guild_id": guild_id})
        revision = revision_doc.get("revision", 0) if revision_doc else 0
        key = f"config:{guild_id}:{revision}"
        cached = await CacheService.get(key)
        if cached:
            return GuildConfig(**cached)

        # Fallback to DB
        doc = revision_doc
        if doc:
            config = GuildConfig(**doc)
            # Cannot dump Pydantic object directly with model_dump (Pydantic v2)
            # So we use simple dict serialization
            data = config.model_dump(by_alias=True)
            # ensure _id string format
            data["_id"] = str(data["_id"])
            await CacheService.set(key, data, 3600)
            return config

        # Create default
        await cls.repo.update_one(
            {"guild_id": guild_id}, {"$setOnInsert": {"guild_id": guild_id}}, upsert=True
        )
        default_config = await cls.repo.find_one({"guild_id": guild_id})

        obj = GuildConfig(**default_config)
        await CacheService.set(key, obj.model_dump(by_alias=True), 3600)
        return obj

    @classmethod
    async def update_guild_config(cls, guild_id: int, updates: dict):
        current = await cls.get_guild_config(guild_id)
        forbidden = {"id", "_id", "guild_id"}
        if forbidden.intersection(updates) or set(updates) - set(GuildConfig.model_fields):
            raise ValueError("Unknown or immutable configuration field.")
        validated = GuildConfig(**{**current.model_dump(by_alias=True), **updates})
        updates = {key: validated.model_dump()[key] for key in updates}
        await cls.repo.update_one(
            {"guild_id": guild_id}, {"$set": updates, "$inc": {"revision": 1}}, upsert=True
        )
