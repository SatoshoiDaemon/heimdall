import pytest

from src.core.redis_client import RedisClient
from src.models.domain import GuildConfig
from src.services.cache_service import CacheService
from src.services.config_service import ConfigService


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value
        return True

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
        return len(keys)

    async def keys(self, pattern):
        prefix = pattern.removesuffix("*")
        return [key for key in self.values if key.startswith(prefix)]


class FakeConfigRepository:
    def __init__(self):
        self.documents = {}

    async def find_one(self, query):
        return self.documents.get(query["guild_id"])

    async def insert_one(self, document):
        document = {"_id": "generated-id", **document}
        self.documents[document["guild_id"]] = document
        return document["_id"]

    async def update_one(self, query, update, upsert=False):
        document = self.documents.get(query["guild_id"], {"_id": "generated-id", **query})
        document.update(update.get("$set", update.get("$setOnInsert", {})))
        self.documents[query["guild_id"]] = document


@pytest.mark.asyncio
async def test_cache_set_get_and_invalidate(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(RedisClient, "redis_conn", redis)

    await CacheService.set("key", {"value": 1})
    assert await CacheService.get("key") == {"value": 1}
    await CacheService.delete("key")
    assert await CacheService.get("key") is None


@pytest.mark.asyncio
async def test_config_service_creates_and_caches_default(monkeypatch):
    redis = FakeRedis()
    repository = FakeConfigRepository()
    monkeypatch.setattr(RedisClient, "redis_conn", redis)
    monkeypatch.setattr(ConfigService, "repo", repository)

    config = await ConfigService.get_guild_config(123)
    cached = await ConfigService.get_guild_config(123)

    assert isinstance(config, GuildConfig)
    assert cached.guild_id == 123
    assert await redis.get("config:123:0") is not None
