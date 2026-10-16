import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from src.cogs.moderation import PaginationView
from src.core.exceptions import InvalidTarget, ModerationError
from src.dtos.payloads import LogEventDTO, SpamEventDTO, WarnRequestDTO
from src.models.domain import GuildConfig
from src.services.anti_abuse_service import AntiAbuseService
from src.services.automod_service import AutoModService
from src.services.captcha_service import CaptchaService
from src.services.config_service import ConfigService
from src.services.log_service import LogService
from src.services.moderation_service import ModerationService as Mod
from src.services.rbac_service import RBACService


class Role:
    def __init__(self, position, permissions=None):
        self.position = position
        self.id = position
        self.permissions = permissions or discord.Permissions.none()
        self.managed = False

    def is_default(self):
        return False

    def __le__(self, other):
        return self.position <= other.position

    def __ge__(self, other):
        return self.position >= other.position


def make_guild():
    permissions = discord.Permissions.all()
    bot = SimpleNamespace(id=100, top_role=Role(100), guild_permissions=permissions, roles=[])
    moderator = SimpleNamespace(id=20, top_role=Role(50), guild_permissions=permissions, roles=[])
    target = SimpleNamespace(
        id=10,
        top_role=Role(10),
        guild_permissions=discord.Permissions.none(),
        roles=[],
        add_roles=AsyncMock(),
        timeout=AsyncMock(),
        bot=False,
    )
    role = Role(2)
    members = {100: bot, 20: moderator, 10: target}
    guild = SimpleNamespace(
        id=1,
        owner_id=999,
        me=bot,
        get_member=members.get,
        get_role=lambda role_id: role if role_id == role.id else None,
        ban=AsyncMock(),
        unban=AsyncMock(),
        kick=AsyncMock(),
    )
    channel = SimpleNamespace(
        id=30,
        guild=guild,
        send=AsyncMock(),
        purge=AsyncMock(return_value=[1, 2]),
        permissions_for=lambda member: permissions,
        get_partial_message=lambda mid: SimpleNamespace(delete=AsyncMock()),
    )
    guild.get_channel = lambda cid: channel if cid == 30 else None
    guild.fetch_ban = AsyncMock(
        side_effect=discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "not banned")
    )
    return guild, target, moderator, role, channel


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 5, 6, 20])
async def test_warning_pages(count):
    pages = max(1, (count + 4) // 5)
    for page in range(1, pages + 1):
        view = PaginationView("Warnings", [str(i) for i in range(count)], page=page)
        assert view.page == page - 1
        assert view.previous.disabled == (page == 1)
        assert view.next.disabled == (page == pages)
        assert view.page_count == pages
        assert view.embed().description
    for invalid in (0, -1, pages + 1):
        with pytest.raises(ModerationError):
            PaginationView("Warnings", [str(i) for i in range(count)], page=invalid)


@pytest.mark.asyncio
async def test_warning_navigation():
    view = PaginationView("Warnings", list(map(str, range(20))))
    interaction = SimpleNamespace(response=SimpleNamespace(edit_message=AsyncMock()))
    for _ in range(8):
        await view._update(interaction, 1)
    assert view.page == 3
    for _ in range(8):
        await view._update(interaction, -1)
    assert view.page == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["none", "role_missing", "forbidden", "expired", "wrong", "reused"]
)
async def test_captcha_completion(backend, failure):
    db, _ = backend
    guild, member, _, role, _ = make_guild()
    await ConfigService.update_guild_config(1, {"verified_role_id": role.id})
    code, _ = await CaptchaService.create_session(1, member.id)
    if failure == "role_missing":
        guild.get_role = lambda _: None
    if failure == "forbidden":
        member.add_roles.side_effect = discord.Forbidden(
            SimpleNamespace(status=403, reason="Forbidden"), "denied"
        )
    if failure == "expired":
        await db.captcha_sessions.delete_one({"_id": "1:10"})
    if failure in {"role_missing", "forbidden"}:
        with pytest.raises(ModerationError):
            await CaptchaService.complete(guild, member, code)
        assert (await db.captcha_sessions.find_one({"_id": "1:10"}))["consumed"] is False
        member.add_roles.side_effect = None
        guild.get_role = lambda _: role
        assert await CaptchaService.complete(guild, member, code)
    elif failure in {"expired", "wrong"}:
        assert not await CaptchaService.complete(
            guild, member, "BAD" if failure == "wrong" else code
        )
        member.add_roles.assert_not_awaited()
    else:
        assert await CaptchaService.complete(guild, member, code)
        member.add_roles.assert_awaited_once()
        assert not await CaptchaService.complete(guild, member, code)


@pytest.mark.asyncio
async def test_captcha_crash_after_role_assignment(backend):
    db, _ = backend
    guild, member, _, role, _ = make_guild()
    member.roles = [role]
    await ConfigService.update_guild_config(1, {"verified_role_id": role.id})
    code, _ = await CaptchaService.create_session(1, 10)
    assert await CaptchaService.complete(guild, member, code)
    member.add_roles.assert_not_awaited()
    assert (await db.captcha_sessions.find_one({"_id": "1:10"}))["consumed"] is True


@pytest.mark.parametrize(
    "kind", ["below", "same", "admin", "owner_target", "self", "bot", "bot_below", "timeout_admin"]
)
def test_hierarchy(kind):
    guild, target, moderator, _, _ = make_guild()
    if kind in {"below", "same", "admin"}:
        moderator.top_role = Role(9 if kind == "below" else 10)
    elif kind == "owner_target":
        target.id = guild.owner_id
    elif kind == "self":
        target.id = moderator.id
    elif kind == "bot":
        target.id = guild.me.id
    elif kind == "bot_below":
        guild.me.top_role = Role(5)
    elif kind == "timeout_admin":
        target.guild_permissions = discord.Permissions(administrator=True)
    with pytest.raises(InvalidTarget):
        Mod._ensure_member_target(guild, target, moderator.id, timeout=kind == "timeout_admin")


def test_owner_can_act_below_bot_hierarchy():
    guild, target, moderator, _, _ = make_guild()
    guild.owner_id = moderator.id
    moderator.top_role = Role(1)
    Mod._ensure_member_target(guild, target, moderator.id)


@pytest.mark.asyncio
async def test_rbac_does_not_bypass_hierarchy(backend):
    guild, target, moderator, _, _ = make_guild()
    moderator.guild_permissions = discord.Permissions.none()
    moderator.top_role = Role(1)
    await RBACService.set_user_permission(1, moderator.id, ["timeout"])
    with pytest.raises(InvalidTarget):
        await Mod.timeout(guild, target, moderator.id, 60, "test")
    target.timeout.assert_not_awaited()


@pytest.mark.asyncio
async def test_spam_concurrency_cooldown_and_weight(backend):
    db, _ = backend
    hits = await asyncio.gather(
        *(
            AntiAbuseService.track_spam(SpamEventDTO(1, 10, i, 30, "message", weight=2), 10, 60)
            for i in range(100)
        )
    )
    assert sum(hits) == 1
    AntiAbuseService._windows.clear()
    dto = SpamEventDTO(1, 10, 101, 30, "message", weight=2)
    assert await AntiAbuseService.track_spam(dto, 2, 60)


@pytest.mark.asyncio
async def test_warn_recovers_partial_projection(backend, monkeypatch):
    db, _ = backend
    original = Mod.warn_repo.update_one
    monkeypatch.setattr(
        Mod.warn_repo, "update_one", AsyncMock(side_effect=RuntimeError("db failed"))
    )
    with pytest.raises(RuntimeError):
        await Mod.issue_warn(WarnRequestDTO(1, 10, 20, "Spam"))
    assert (await db.cases.find_one({}))["status"] == "pending"
    monkeypatch.setattr(Mod.warn_repo, "update_one", original)
    guild, *_ = make_guild()
    await Mod.reconcile(SimpleNamespace(get_guild=lambda _: guild))
    await Mod.reconcile(SimpleNamespace(get_guild=lambda _: guild))
    assert (await db.cases.find_one({}))["status"] == "completed"
    assert await db.warns.count_documents({}) == 1
    assert await db.audit_outbox.count_documents({}) == 1


@pytest.mark.asyncio
async def test_timeout_recovers_after_discord_success(backend, monkeypatch):
    db, _ = backend
    guild, target, moderator, _, _ = make_guild()
    finish = Mod._finish
    monkeypatch.setattr(Mod, "_finish", AsyncMock(side_effect=RuntimeError("db failed")))
    with pytest.raises(RuntimeError):
        await Mod.timeout(guild, target, moderator.id, 60, "test")
    assert (await db.cases.find_one({}))["status"] == "applied"
    monkeypatch.setattr(Mod, "_finish", finish)
    await Mod.reconcile(SimpleNamespace(get_guild=lambda _: guild))
    target.timeout.assert_awaited_once()
    assert (await db.cases.find_one({}))["status"] == "completed"
    assert await db.punishments.count_documents({}) == 1


@pytest.mark.asyncio
async def test_purge_interrupted_is_not_replayed(backend):
    db, _ = backend
    guild, _, moderator, _, channel = make_guild()
    channel.purge.side_effect = TimeoutError("unknown result")
    with pytest.raises(TimeoutError):
        await Mod.purge(channel, moderator.id, 5, "cleanup")
    await Mod.reconcile(SimpleNamespace(get_guild=lambda _: guild))
    channel.purge.assert_awaited_once()
    assert (await db.cases.find_one({}))["status"] == "uncertain"


@pytest.mark.asyncio
async def test_automod_consumer_creates_single_case(backend):
    db, _ = backend
    guild, member, _, _, channel = make_guild()
    await ConfigService.update_guild_config(
        1, {"automod_rules": {"words": {"enabled": True, "action": "warn"}}}
    )
    message = SimpleNamespace(id=7, guild=guild, author=member, channel=channel)
    first = await AutoModService.consume(message, "words")
    second = await AutoModService.consume(message, "words")
    assert first.case_number == second.case_number
    assert first.origin == "automatic"
    assert await db.cases.count_documents({}) == 1
    await ConfigService.update_guild_config(1, {"automod_rules": {"words": {"enabled": False}}})
    message.id = 8
    assert await AutoModService.consume(message, "words") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["timeout", "delete"])
async def test_automod_actions(backend, action):
    db, _ = backend
    guild, member, _, _, channel = make_guild()
    await ConfigService.update_guild_config(
        1, {"automod_rules": {"words": {"enabled": True, "action": action}}}
    )
    result = await AutoModService.consume(
        SimpleNamespace(id=9, guild=guild, author=member, channel=channel), "words"
    )
    assert result.status == "completed"
    assert result.action == action.upper()
    assert await db.cases.count_documents({}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rule,content,expected",
    [
        ("words", "blocked now", True),
        ("words", "unblocked", False),
        ("urls", "https://example.com", True),
        ("invites", "discord.com/invite/test", True),
    ],
)
async def test_configurable_filters(backend, rule, content, expected):
    guild, member, _, _, channel = make_guild()
    message = SimpleNamespace(
        id=1,
        guild=guild,
        author=member,
        channel=channel,
        content=content,
        mentions=[],
        role_mentions=[],
        mention_everyone=False,
    )
    settings = GuildConfig(
        _id="test", guild_id=1, blocked_words=["blocked"], automod_rules={rule: {"enabled": True}}
    )
    assert bool(await AntiAbuseService.detect(message, settings)) == expected
    settings.exempt_channel_ids = [channel.id]
    assert not await AntiAbuseService.detect(message, settings)


@pytest.mark.asyncio
async def test_audit_retries_and_dead_letter(backend, monkeypatch):
    db, _ = backend
    event_id = await LogService.enqueue_log(LogEventDTO(1, "test", "payload", 0), "stable-id")
    await LogService.enqueue_log(LogEventDTO(1, "test", "payload", 0), "stable-id")
    monkeypatch.setattr(LogService, "_send", AsyncMock(side_effect=RuntimeError("HTTP failure")))
    for _ in range(5):
        await db.audit_outbox.update_one(
            {"_id": event_id}, {"$set": {"next_attempt": datetime.now(UTC) - timedelta(seconds=1)}}
        )
        assert not await LogService.deliver(None, event_id)
    entry = await db.audit_outbox.find_one({"_id": event_id})
    assert entry["dead"] and not entry["delivered"] and entry["attempts"] == 5
    assert await db.audit_failures.count_documents({}) == 1
    assert await db.audit_outbox.count_documents({}) == 1


@pytest.mark.asyncio
async def test_local_queue_worker_restart_and_delivery(backend, monkeypatch):
    db, _ = backend
    event_id = await LogService.enqueue_log(LogEventDTO(1, "test", "payload", 0))
    monkeypatch.setattr(LogService, "_send", AsyncMock(return_value="sent"))
    await LogService.run_once(None)
    assert (await db.audit_outbox.find_one({"_id": event_id}))["delivered"]
    await LogService.run_once(None)
    LogService._send.assert_awaited_once()
    assert LogService._queue.qsize() == 0


@pytest.mark.asyncio
async def test_outbox_recovers_local_queue_loss(backend, monkeypatch):
    db, _ = backend
    event_id = await LogService.enqueue_log(LogEventDTO(1, "test", "payload", 0))
    LogService.reset_queue()
    monkeypatch.setattr(LogService, "_send", AsyncMock(return_value="sent"))
    await LogService.run_once(None)
    assert (await db.audit_outbox.find_one({"_id": event_id}))["delivered"]


@pytest.mark.asyncio
async def test_audit_delivery_lease_excludes_parallel_workers(backend, monkeypatch):
    event_id = await LogService.enqueue_log(LogEventDTO(1, "test", "payload", 0))

    async def slow(*args):
        await asyncio.sleep(0.01)
        return "sent"

    send = AsyncMock(side_effect=slow)
    monkeypatch.setattr(LogService, "_send", send)
    await asyncio.gather(*(LogService.deliver(None, event_id) for _ in range(10)))
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_case_filters_and_database_pages(backend):
    db, _ = backend
    for i in range(12):
        await Mod.issue_warn(WarnRequestDTO(1, 10, 20 if i % 2 else 21, "warn"))
    rows = await Mod.history(
        1, moderator_id=20, action="WARN", origin="manual", page=1, page_size=5
    )
    assert len(rows) == 5
    assert len(await Mod.history(1, moderator_id=20, page=2, page_size=5)) == 1
    assert await db.cases.count_documents({}) == 12


@pytest.mark.asyncio
async def test_config_invalidation_ignores_stale_cache(backend):
    db, _ = backend
    await ConfigService.get_guild_config(1)
    await ConfigService.update_guild_config(1, {"anti_spam_enabled": True})
    from src.services.cache_service import CacheService

    assert await CacheService.get("config:1") is None
    assert (await ConfigService.get_guild_config(1)).anti_spam_enabled
    with pytest.raises(ValueError):
        await ConfigService.update_guild_config(1, {"spam_threshold_score": 0})


@pytest.mark.asyncio
async def test_pending_action_blocks_newer_action_until_recovered(backend, monkeypatch):
    guild, target, moderator, _, _ = make_guild()
    original = Mod._finish
    monkeypatch.setattr(Mod, "_finish", AsyncMock(side_effect=RuntimeError("interrupted")))
    with pytest.raises(RuntimeError):
        await Mod.timeout(guild, target, moderator.id, 600, "first")
    monkeypatch.setattr(Mod, "_finish", original)
    with pytest.raises(ModerationError, match="recovered or reviewed"):
        await Mod.timeout(guild, target, moderator.id, 60, "second")
    target.timeout.assert_awaited_once()
    await Mod.reconcile(SimpleNamespace(get_guild=lambda _: guild))
    newer = await Mod.timeout(guild, target, moderator.id, 60, "second")
    assert newer.status == "completed"
    assert target.timeout.await_count == 2


@pytest.mark.asyncio
async def test_new_timeout_supersedes_previous_case(backend):
    guild, target, moderator, _, _ = make_guild()
    older = await Mod.timeout(guild, target, moderator.id, 60, "old")
    newer = await Mod.timeout(guild, target, moderator.id, 120, "new")
    assert not (await Mod.get_case(1, older.case_number)).active
    assert (
        await Mod.case_repo.get_latest_active(1, target.id, "TIMEOUT")
    ).case_number == newer.case_number
    with pytest.raises(ModerationError):
        await Mod.untimeout(guild, target, moderator.id, older.case_number, "old reversal")
    reversal = await Mod.untimeout(guild, target, moderator.id, newer.case_number, "remove")
    repeated = await Mod.untimeout(guild, target, moderator.id, newer.case_number, "remove")
    assert reversal.case_number == repeated.case_number
    assert target.timeout.await_count == 3


@pytest.mark.asyncio
async def test_config_callbacks_revalidate_revoked_permission(backend):
    from src.cogs.config_ui import ConfigView

    guild, _, moderator, _, _ = make_guild()
    moderator.guild_permissions = discord.Permissions.none()
    settings = await ConfigService.get_guild_config(guild.id)
    view = ConfigView(settings, moderator.id)
    interaction = SimpleNamespace(
        guild=guild,
        guild_id=guild.id,
        user=moderator,
        response=SimpleNamespace(send_message=AsyncMock()),
    )
    assert not await view.interaction_check(interaction)
    interaction.response.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_captcha_rejects_elevated_verified_role(backend):
    db, _ = backend
    guild, member, _, role, _ = make_guild()
    role.permissions = discord.Permissions(manage_messages=True)
    await ConfigService.update_guild_config(guild.id, {"verified_role_id": role.id})
    code, _ = await CaptchaService.create_session(1, 10)
    with pytest.raises(ModerationError, match="elevated"):
        await CaptchaService.complete(guild, member, code)
    member.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_timeout_expiry_marks_case_and_projection_inactive(backend):
    db, _ = backend
    guild, target, moderator, _, _ = make_guild()
    case = await Mod.timeout(guild, target, moderator.id, 60, "temporary")
    await db.cases.update_one(
        {"case_number": case.case_number},
        {"$set": {"metadata.until": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}},
    )
    await Mod.expire_timeouts()
    assert not (await Mod.get_case(1, case.case_number)).active
    assert not (await db.punishments.find_one({"case_number": case.case_number}))["active"]


@pytest.mark.asyncio
async def test_event_detection_dispatches_to_consumer_and_case(backend):
    from src.cogs.events import EventListener

    db, _ = backend
    guild, target, _, _, channel = make_guild()
    await ConfigService.update_guild_config(
        1,
        {
            "blocked_words": ["blocked"],
            "automod_rules": {"words": {"enabled": True, "action": "warn"}},
        },
    )
    cog = EventListener(None)
    await cog.cog_load()
    message = SimpleNamespace(
        id=1000,
        guild=guild,
        author=target,
        channel=channel,
        content="blocked",
        mentions=[],
        role_mentions=[],
        mention_everyone=False,
    )
    await cog.on_message(message)
    await cog.cog_unload()
    case = await db.cases.find_one({})
    assert case["origin"] == "automatic" and case["status"] == "completed"
