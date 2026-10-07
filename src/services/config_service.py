from src.repositories.bot_repos import ConfigRepository
from src.services.cache_service import CacheService
from src.models.domain import GuildConfig

class ConfigService:
    repo = ConfigRepository()

    @classmethod
    async def get_guild_config(cls, guild_id: int) -> GuildConfig:
        key = f"config:{guild_id}"
        cached = await CacheService.get(key)
        if cached:
            return GuildConfig(**cached)
        
        # Fallback to DB
        doc = await cls.repo.find_one({"guild_id": guild_id})
        if doc:
            config = GuildConfig(**doc)
            # Cannot dump Pydantic object directly with model_dump (Pydantic v2)
            # So we use simple dict serialization
            data = config.model_dump(by_alias=True)
            # ensure _id string format
            data['_id'] = str(data['_id'])
            await CacheService.set(key, data, 3600)
            return config
            
        # Create default
        default_config = {"guild_id": guild_id}
        inserted_id = await cls.repo.insert_one(default_config)
        default_config["_id"] = str(inserted_id)
        
        obj = GuildConfig(**default_config)
        await CacheService.set(key, obj.model_dump(by_alias=True), 3600)
        return obj

    @classmethod
    async def update_guild_config(cls, guild_id: int, updates: dict):
        await cls.repo.upsert_config(guild_id, updates)
        await CacheService.invalidate_guild_config(guild_id)
