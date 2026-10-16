import pytest

from src.core.event_bus import EventBus


@pytest.fixture(autouse=True)
def reset_event_bus():
    EventBus._listeners.clear()
    yield
    EventBus._listeners.clear()


@pytest.fixture(autouse=True)
def reset_local_state():
    from src.services.anti_abuse_service import AntiAbuseService
    from src.services.cache_service import CacheService
    from src.services.lock_service import LockService
    from src.services.log_service import LogService

    CacheService.clear()
    AntiAbuseService._windows.clear()
    LockService._resources.clear()
    LogService.reset_queue()
    yield
    CacheService.clear()
    AntiAbuseService._windows.clear()
    LockService._resources.clear()
    LogService.reset_queue()


@pytest.fixture
async def backend(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient

    from src.core.config import config
    from src.core.database import Database

    db = AsyncMongoMockClient().test
    monkeypatch.setattr(Database, "db", db)
    monkeypatch.setattr(Database, "transactions_supported", False)
    monkeypatch.setattr(config, "CAPTCHA_TIMEOUT_SECONDS", 300)
    yield db, None
