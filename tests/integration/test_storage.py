"""Use any configured MongoDB instance; no auxiliary service is needed."""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from src.core.database import Database
from src.dtos.payloads import LogEventDTO, WarnRequestDTO
from src.services.captcha_service import CaptchaService
from src.services.config_service import ConfigService
from src.services.log_service import LogService
from src.services.moderation_service import ModerationService as Mod
from tests.test_reliability import make_guild

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("HEIMDALL_INTEGRATION") != "1",
        reason="Set HEIMDALL_INTEGRATION=1 and TEST_MONGO_URI",
    ),
]


@pytest.fixture
async def services(monkeypatch):
    client = AsyncIOMotorClient(
        os.environ.get("TEST_MONGO_URI", "mongodb://localhost:27017"),
        serverSelectionTimeoutMS=5000,
        tz_aware=True,
    )
    db = client["heimdall_test_" + uuid.uuid4().hex]
    hello = await db.command("hello")
    monkeypatch.setattr(Database, "client", client)
    monkeypatch.setattr(Database, "db", db)
    monkeypatch.setattr(Database, "transactions_supported", bool(hello.get("setName")))
    await Database.ensure_indexes()
    yield db
    await client.drop_database(db.name)
    client.close()


async def test_case_counters_under_concurrency(services):
    cases = await asyncio.gather(
        *(
            Mod.case_repo.create_case(
                guild_id=1, action="NOTE", target_user_id=10, moderator_id=20, reason="test"
            )
            for _ in range(50)
        )
    )
    assert len({case.case_number for case in cases}) == 50


async def test_warn_failure_and_restart_recovery(services, monkeypatch):
    original = LogService.enqueue_log
    monkeypatch.setattr(
        LogService, "enqueue_log", AsyncMock(side_effect=RuntimeError("after projection"))
    )
    with pytest.raises(RuntimeError):
        await Mod.issue_warn(WarnRequestDTO(1, 10, 20, "spam"))
    assert (await services.cases.find_one({}))["status"] == "pending"
    assert await services.warns.count_documents({}) == (0 if Database.transactions_supported else 1)
    monkeypatch.setattr(LogService, "enqueue_log", original)
    guild, *_ = make_guild()
    await Mod.reconcile(SimpleNamespace(get_guild=lambda _: guild))
    assert await services.warns.count_documents({}) == 1
    assert (await services.cases.find_one({}))["status"] == "completed"


async def test_timeout_after_discord_success_is_not_replayed(services, monkeypatch):
    guild, target, moderator, *_ = make_guild()
    finish = Mod._finish
    monkeypatch.setattr(Mod, "_finish", AsyncMock(side_effect=RuntimeError("projection failed")))
    with pytest.raises(RuntimeError):
        await Mod.timeout(guild, target, moderator.id, 60, "test")
    monkeypatch.setattr(Mod, "_finish", finish)
    await Mod.reconcile(SimpleNamespace(get_guild=lambda _: guild))
    target.timeout.assert_awaited_once()
    assert (await services.cases.find_one({}))["status"] == "completed"


async def test_concurrent_reversals_are_idempotent(services):
    case = await Mod.issue_warn(WarnRequestDTO(1, 10, 20, "spam"))
    reversals = await asyncio.gather(
        *(Mod.unwarn(1, 20, case.case_number, "cleared") for _ in range(10))
    )
    assert len({c.case_number for c in reversals}) == 1
    assert await services.cases.count_documents({}) == 2


async def test_pending_audit_survives_queue_loss(services, monkeypatch):
    event_id = await LogService.enqueue_log(LogEventDTO(1, "restart", "test", 0))
    LogService.reset_queue()
    monkeypatch.setattr(LogService, "_send", AsyncMock(return_value="sent"))
    await LogService.run_once(None)
    assert (await services.audit_outbox.find_one({"_id": event_id}))["delivered"]
    await LogService.run_once(None)
    LogService._send.assert_awaited_once()


async def test_failed_delivery_retries_without_loss(services, monkeypatch):
    event_id = await LogService.enqueue_log(LogEventDTO(1, "HTTP failure", "test", 0))
    monkeypatch.setattr(LogService, "_send", AsyncMock(side_effect=TimeoutError()))
    await LogService.run_once(None)
    assert not (await services.audit_outbox.find_one({"_id": event_id}))["delivered"]
    monkeypatch.setattr(LogService, "_send", AsyncMock(return_value="sent"))
    await services.audit_outbox.update_one(
        {"_id": event_id}, {"$set": {"next_attempt": datetime.now(UTC) - timedelta(seconds=1)}}
    )
    LogService.reset_queue()
    await LogService.run_once(None)
    assert (await services.audit_outbox.find_one({"_id": event_id}))["delivered"]


async def test_captcha_uses_mongo_expiration_and_survives_restart(services):
    guild, member, _, role, _ = make_guild()
    await ConfigService.update_guild_config(1, {"verified_role_id": role.id})
    code, _ = await CaptchaService.create_session(1, member.id)
    assert await CaptchaService.complete(guild, member, code)
    assert not await CaptchaService.complete(guild, member, code)
    member.add_roles.assert_awaited_once()
    assert (await services.captcha_sessions.index_information())["expires_at_1"][
        "expireAfterSeconds"
    ] == 0


async def test_captcha_expiry_does_not_depend_on_ttl_sweeper(services):
    guild, member, _, role, _ = make_guild()
    await ConfigService.update_guild_config(1, {"verified_role_id": role.id})
    code, _ = await CaptchaService.create_session(1, member.id)
    await services.captcha_sessions.update_one(
        {"_id": "1:10"}, {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}}
    )
    assert not await CaptchaService.complete(guild, member, code)
    member.add_roles.assert_not_awaited()
