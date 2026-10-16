import pytest
from mongomock_motor import AsyncMongoMockClient

from src.core.database import Database
from src.services.cache_service import CacheService
from src.services.config_service import ConfigService


@pytest.mark.asyncio
async def test_cache_set_get_and_invalidate():
    await CacheService.set("key", {"value": [1]})
    result = await CacheService.get("key")
    result["value"].append(2)
    assert await CacheService.get("key") == {"value": [1]}
    await CacheService.delete("key")
    assert await CacheService.get("key") is None


@pytest.mark.asyncio
async def test_config_service_creates_and_caches_default(monkeypatch):
    db = AsyncMongoMockClient().test
    monkeypatch.setattr(Database, "db", db)
    settings = await ConfigService.get_guild_config(123)
    assert settings.guild_id == 123
    assert await CacheService.get("config:123") is not None
    await ConfigService.update_guild_config(123, {"anti_spam_enabled": True})
    assert (await ConfigService.get_guild_config(123)).anti_spam_enabled
