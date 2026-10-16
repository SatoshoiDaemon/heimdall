import asyncio
from unittest.mock import AsyncMock

import pytest

from src.core.bot import ModBot
from src.core.database import Database
from src.core.event_bus import EventBus
from src.core.exceptions import ModBotException
from src.dtos.payloads import LogEventDTO, SpamEventDTO, WarnRequestDTO
from src.services.anti_abuse_service import AntiAbuseService
from src.services.cache_service import CacheService
from src.services.captcha_service import CaptchaService
from src.services.config_service import ConfigService
from src.services.lock_service import LockService
from src.services.log_service import LogService
from src.services.moderation_service import ModerationService as Mod
from src.services.rbac_service import RBACService
from tests.test_reliability import make_guild


@pytest.mark.asyncio
async def test_local_cache_ttl_limit_and_guild_isolation(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("src.services.cache_service.monotonic", lambda: clock[0])
    monkeypatch.setattr(CacheService, "MAX_ENTRIES", 2)
    await CacheService.set("config:1", {"v": 1}, 5)
    await CacheService.set("config:10", {"v": 10}, 5)
    await CacheService.invalidate_guild_config(1)
    assert await CacheService.get("config:10") == {"v": 10}
    await CacheService.set("b", {"v": 2}, 5)
    await CacheService.set("c", {"v": 3}, 5)
    assert len(CacheService._entries) == 2
    clock[0] += 6
    CacheService.cleanup()
    assert not CacheService._entries


@pytest.mark.asyncio
async def test_local_spam_expiry_duplicates_and_memory_bound(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("src.services.anti_abuse_service.monotonic", lambda: clock[0])
    monkeypatch.setattr(AntiAbuseService, "MAX_WINDOWS", 2)
    dto = SpamEventDTO(1, 2, 1, 4, "test", 2)
    assert not await AntiAbuseService.track_spam(dto, 4, 10)
    assert not await AntiAbuseService.track_spam(dto, 4, 10)
    clock[0] += 11
    assert not await AntiAbuseService.track_spam(SpamEventDTO(1, 2, 2, 4, "test", 2), 4, 10)
    assert await AntiAbuseService.track_spam(SpamEventDTO(1, 2, 3, 4, "test", 2), 4, 10)
    for user in range(10):
        await AntiAbuseService.track_spam(SpamEventDTO(1, user, user, 4, "test"), 4, 10)
    assert len(AntiAbuseService._windows) <= 2
    clock[0] += 11
    AntiAbuseService.cleanup()
    assert not AntiAbuseService._windows


@pytest.mark.asyncio
async def test_locks_serialize_and_remove_idle_resources():
    running = 0
    highest = 0

    async def operation():
        nonlocal running, highest
        async with LockService.get_lock("same"):
            running += 1
            highest = max(highest, running)
            await asyncio.sleep(0)
            running -= 1

    await asyncio.gather(*(operation() for _ in range(30)))
    assert highest == 1
    assert not LockService._resources


@pytest.mark.asyncio
async def test_lock_waiter_cancellation_and_resource_bound(monkeypatch):
    monkeypatch.setattr(LockService, "MAX_RESOURCES", 1)
    async with LockService.get_lock("busy"):
        with pytest.raises(ModBotException, match="Too many"):
            async with LockService.get_lock("another"):
                pass

        async def waiter():
            async with LockService.get_lock("busy"):
                pass

        task = asyncio.create_task(waiter())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ModBotException, match="busy"):
            async with LockService.get_lock("busy", timeout=0.001):
                pass
    assert not LockService._resources


@pytest.mark.asyncio
async def test_rbac_revocation_invalidates_local_cache(backend):
    await RBACService.set_user_permission(1, 10, ["ban"])
    assert await RBACService.has_permission(1, 10, [], "ban")
    await RBACService.set_user_permission(1, 10, [])
    assert not await RBACService.has_permission(1, 10, [], "ban")
    await RBACService.set_role_permission(1, 2, ["warn"])
    assert await RBACService.has_permission(1, 10, [2], "warn")
    await RBACService.set_role_permission(1, 2, [])
    assert not await RBACService.has_permission(1, 10, [2], "warn")


@pytest.mark.asyncio
async def test_audit_queue_overflow_keeps_records_durable(backend, monkeypatch):
    db, _ = backend
    monkeypatch.setattr(LogService, "QUEUE_SIZE", 1)
    LogService.reset_queue()
    for _ in range(3):
        await LogService.enqueue_log(LogEventDTO(1, "test", "durable", 0))
    assert LogService._queue.qsize() == 1
    assert await db.audit_outbox.count_documents({}) == 3
    monkeypatch.setattr(LogService, "_send", AsyncMock(return_value="sent"))
    for _ in range(3):
        await LogService.run_once(None)
    assert await db.audit_outbox.count_documents({"delivered": True}) == 3


@pytest.mark.asyncio
async def test_captcha_attempt_limit(backend):
    guild, member, _, role, _ = make_guild()
    await ConfigService.update_guild_config(1, {"verified_role_id": role.id})
    code, _ = await CaptchaService.create_session(1, 10)
    for _ in range(5):
        assert not await CaptchaService.complete(guild, member, "WRONG")
    assert not await CaptchaService.complete(guild, member, code)
    member.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_discord_operation_does_not_create_duplicate_case(backend):
    db, _ = backend
    token = Mod.operation_id.set("discord:123")
    try:
        first = await Mod.issue_warn(WarnRequestDTO(1, 10, 20, "same command"))
        again = await Mod.issue_warn(WarnRequestDTO(1, 10, 20, "same command"))
    finally:
        Mod.operation_id.reset(token)
    assert first.case_number == again.case_number
    assert await db.cases.count_documents({}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["mongo", "cog", "sync", "success"])
async def test_startup_and_ordered_shutdown(monkeypatch, stage):
    bot = ModBot()
    await bot._async_setup_hook()
    connect = AsyncMock(side_effect=RuntimeError("offline") if stage == "mongo" else None)
    close = AsyncMock()
    monkeypatch.setattr(Database, "connect", connect)
    monkeypatch.setattr(Database, "close", close)
    bot.load_extension = AsyncMock(side_effect=RuntimeError("bad cog") if stage == "cog" else None)
    bot.tree.sync = AsyncMock(side_effect=RuntimeError("bad sync") if stage == "sync" else None)

    async def hold(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(LogService, "worker", hold)
    monkeypatch.setattr(bot, "maintenance", hold)
    if stage == "success":
        await bot.setup_hook()
        assert bot.load_extension.await_count == 4
        assert not bot._bg_task.done()
    else:
        with pytest.raises(RuntimeError):
            await bot.setup_hook()
        assert not hasattr(bot, "_bg_task")
    await bot.close()
    await bot.close()
    close.assert_awaited_once()
    if stage == "success":
        assert bot._bg_task.done() and bot._maintenance_task.done()


@pytest.mark.asyncio
async def test_event_bus_drain_is_bounded():
    async def never():
        await asyncio.Event().wait()

    EventBus.subscribe("slow", never)
    EventBus.emit("slow")
    await asyncio.sleep(0)
    await EventBus.drain(timeout=0.001)
    assert not EventBus._tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["warnings", "notes", "history"])
@pytest.mark.parametrize("count", [0, 1, 5, 6, 20, 101])
async def test_database_pages_are_consistent(backend, kind, count):
    from src.cogs.case_views import RecordsView
    from src.core.exceptions import ModerationError
    from src.dtos.payloads import NoteRequestDTO

    for index in range(count):
        if kind == "notes":
            await Mod.add_note(NoteRequestDTO(1, 10, 20, str(index)))
        else:
            await Mod.issue_warn(WarnRequestDTO(1, 10, 20, str(index)))
    filters = {"target_user_id": 10} if kind == "history" else {"user_id": 10}
    pages = max(1, (count + 4) // 5)
    seen = []
    for page in range(1, pages + 1):
        view = RecordsView(1, 20, page, filters, lambda row: str(row.id), kind=kind)
        await view.load()
        assert len(view.rows) <= 5
        assert view.previous.disabled == (page == 1)
        assert view.next.disabled == (page == pages)
        assert len(view.embed().description) <= 4096
        seen.extend(row.id for row in view.rows)
    assert len(seen) == len(set(seen)) == count
    for page in (-1, 0, pages + 1):
        view = RecordsView(1, 20, page, filters, str, kind=kind)
        with pytest.raises(ModerationError):
            await view.load()


@pytest.mark.asyncio
async def test_captcha_recovery_when_consumption_write_fails(backend, monkeypatch):
    db, _ = backend
    guild, member, _, role, _ = make_guild()
    await ConfigService.update_guild_config(1, {"verified_role_id": role.id})
    code, _ = await CaptchaService.create_session(1, 10)
    from types import SimpleNamespace

    await ConfigService.get_guild_config(1)
    collection = db.captcha_sessions
    with monkeypatch.context() as patch:
        patch.setattr(
            Database,
            "db",
            SimpleNamespace(
                captcha_sessions=SimpleNamespace(
                    find_one=collection.find_one,
                    update_one=AsyncMock(side_effect=RuntimeError("Mongo unavailable")),
                )
            ),
        )
        with pytest.raises(RuntimeError):
            await CaptchaService.complete(guild, member, code)
    member.roles = [role]
    assert await CaptchaService.complete(guild, member, code)
    member.add_roles.assert_awaited_once()
