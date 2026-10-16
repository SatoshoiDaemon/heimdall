"""Real services only. Run with HEIMDALL_INTEGRATION=1 pytest -m integration."""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from src.core.database import Database
from src.core.redis_client import RedisClient
from src.dtos.payloads import LogEventDTO, SpamEventDTO, WarnRequestDTO
from src.services.anti_abuse_service import AntiAbuseService
from src.services.lock_service import LockService
from src.services.log_service import LogService
from src.services.moderation_service import ModerationService as Mod
from tests.test_reliability import make_guild

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("HEIMDALL_INTEGRATION") != "1",
        reason="Real services require HEIMDALL_INTEGRATION=1",
    ),
]


@pytest.fixture
async def services(monkeypatch):
    client = AsyncIOMotorClient(
        os.environ.get("TEST_MONGO_URI", "mongodb://localhost:27017/?replicaSet=rs0"),
        serverSelectionTimeoutMS=5000,
        tz_aware=True,
    )
    db = client["heimdall_test_" + uuid.uuid4().hex]
    redis = Redis.from_url(
        os.environ.get("TEST_REDIS_URI", "redis://localhost:6379/15"), decode_responses=True
    )
    await redis.ping()
    hello = await db.command("hello")
    monkeypatch.setattr(Database, "client", client)
    monkeypatch.setattr(Database, "db", db)
    monkeypatch.setattr(Database, "transactions_supported", bool(hello.get("setName")))
    monkeypatch.setattr(RedisClient, "redis_conn", redis)
    await Database.ensure_indexes()
    # Only a dedicated test Redis DB may be used: these tests flush it.
    await redis.flushdb()
    yield db, redis
    await client.drop_database(db.name)
    await redis.flushdb()
    await redis.aclose()
    client.close()


async def test_real_weighted_spam_concurrency_and_expiry(services):
    _, redis = services
    dto = SpamEventDTO(1, 2, 3, 4, "message", 2)
    hits = await asyncio.gather(*(AntiAbuseService.track_spam(dto, 10, 1) for _ in range(50)))
    assert sum(hits) == 1
    await asyncio.sleep(1.1)
    assert not await AntiAbuseService.track_spam(dto, 10, 1)
    assert await redis.ttl("spam:{1:2}:spam") > 0


async def test_case_counters_and_transactions(services):
    db, _ = services
    cases = await asyncio.gather(
        *(
            Mod.case_repo.create_case(
                guild_id=1, action="NOTE", target_user_id=10, moderator_id=20, reason="test"
            )
            for _ in range(50)
        )
    )
    assert len({case.case_number for case in cases}) == 50
    assert Database.transactions_supported
    with pytest.raises(RuntimeError):
        async with Database.transaction():
            await Mod.warn_repo.insert_one({"guild_id": 2, "user_id": 10, "reason": "rollback"})
            raise RuntimeError("rollback")
    assert await db.warns.count_documents({"guild_id": 2}) == 0


async def test_warn_transaction_failure_and_restart_recovery(services, monkeypatch):
    db, _ = services
    original = LogService.enqueue_log
    monkeypatch.setattr(
        LogService, "enqueue_log", AsyncMock(side_effect=RuntimeError("after projection"))
    )
    with pytest.raises(RuntimeError):
        await Mod.issue_warn(WarnRequestDTO(1, 10, 20, "spam"))
    assert await db.warns.count_documents({}) == 0  # rolled back
    assert (await db.cases.find_one({}))["status"] == "pending"
    monkeypatch.setattr(LogService, "enqueue_log", original)
    guild, *_ = make_guild()
    await Mod.reconcile(SimpleNamespace(get_guild=lambda _: guild))
    assert await db.warns.count_documents({}) == 1
    assert (await db.cases.find_one({}))["status"] == "completed"


async def test_lock_contention_and_owned_release(services):
    _, redis = services
    async with LockService.get_lock("test:lock"):
        with pytest.raises(Exception, match="busy"):
            async with LockService.get_lock("test:lock"):
                pytest.fail("lock must not overlap")
        # A stale holder must never delete a replacement owner's lock.
        await redis.set("test:lock", "new-owner")
    assert await redis.get("test:lock") == "new-owner"


async def test_stream_pending_reclaimed_after_crash(services, monkeypatch):
    db, redis = services
    event_id = await LogService.enqueue_log(LogEventDTO(1, "restart", "test", 0))
    await redis.xgroup_create(LogService.QUEUE_KEY, LogService.GROUP, id="0", mkstream=True)
    stream_id = await redis.xadd(LogService.QUEUE_KEY, {"event_id": event_id})
    await redis.xreadgroup(LogService.GROUP, "crashed", {LogService.QUEUE_KEY: ">"})
    await redis.xclaim(
        LogService.QUEUE_KEY, LogService.GROUP, "crashed", 0, [stream_id], idle=61000
    )
    await db.audit_outbox.update_one({"_id": event_id}, {"$set": {"queued_at": datetime.now(UTC)}})
    monkeypatch.setattr(LogService, "_send", AsyncMock(return_value="sent"))
    await LogService.run_once(None, "replacement")
    assert (await db.audit_outbox.find_one({"_id": event_id}))["delivered"]
    assert (await redis.xpending(LogService.QUEUE_KEY, LogService.GROUP))["pending"] == 0
    LogService._send.assert_awaited_once()


async def test_failed_http_delivery_retries_without_loss(services, monkeypatch):
    db, _ = services
    event_id = await LogService.enqueue_log(LogEventDTO(1, "HTTP failure", "test", 0))
    monkeypatch.setattr(LogService, "_send", AsyncMock(side_effect=TimeoutError()))
    await LogService.run_once(None, "worker")
    assert not (await db.audit_outbox.find_one({"_id": event_id}))["delivered"]
    monkeypatch.setattr(LogService, "_send", AsyncMock(return_value="sent"))
    await db.audit_outbox.update_one(
        {"_id": event_id},
        {
            "$set": {
                "next_attempt": datetime.now(UTC) - timedelta(seconds=1),
                "queued_at": datetime.now(UTC) - timedelta(seconds=61),
            }
        },
    )
    await LogService.run_once(None, "worker-after-restart")
    assert (await db.audit_outbox.find_one({"_id": event_id}))["delivered"]


async def test_legacy_list_claim_and_migration_on_real_redis(services):
    import json
    from dataclasses import asdict

    db, redis = services
    raw = json.dumps(asdict(LogEventDTO(1, "legacy", "duplicate payloads are separate events", 0)))
    await redis.lpush("modbot:log_queue", raw, raw)
    await LogService.migrate_legacy()
    assert await db.audit_outbox.count_documents({}) == 2
    assert await redis.llen("modbot:log_queue:migrating") == 0
    assert await redis.llen("modbot:log_queue") == 0


async def test_connection_failure_is_explicit_and_does_not_punish(services, monkeypatch):
    from src.core.exceptions import ModBotException

    failed = Redis.from_url(
        "redis://127.0.0.1:1/0",
        decode_responses=True,
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
    )
    monkeypatch.setattr(RedisClient, "redis_conn", failed)
    try:
        assert not await AntiAbuseService.track_spam(SpamEventDTO(1, 2, 3, 4, "test"), 1, 60)
        with pytest.raises(ModBotException, match="Redis is unavailable"):
            async with LockService.get_lock("unreachable"):
                pytest.fail("must fail closed")
    finally:
        await failed.aclose()
