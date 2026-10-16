from types import SimpleNamespace

import pytest

from src.dtos.payloads import WarnRequestDTO
from src.services.moderation_service import ModerationService


@pytest.fixture
async def moderation_fakes(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient

    from src.core.database import Database

    client = AsyncMongoMockClient()
    monkeypatch.setattr(Database, "db", client.test)
    monkeypatch.setattr(Database, "transactions_supported", False)
    yield client.test


@pytest.mark.asyncio
async def test_warn_and_unwarn_create_related_cases(moderation_fakes):
    db = moderation_fakes
    warning = await ModerationService.issue_warn(WarnRequestDTO(1, 10, 20, "Spam"))
    reversal = await ModerationService.unwarn(1, 20, warning.case_number, "Cleared")
    repeated = await ModerationService.unwarn(1, 20, warning.case_number, "Cleared")
    assert warning.action == "WARN"
    assert reversal.action == "UNWARN"
    assert repeated.case_number == reversal.case_number
    assert reversal.related_case_number == warning.case_number
    assert (await db.cases.find_one({"case_number": warning.case_number}))["revoked"] is True
    assert (await db.warns.find_one({"case_number": warning.case_number}))["revoked"] is True
    assert await db.audit_outbox.count_documents({}) == 2


def test_duration_parser_supports_human_units():
    assert ModerationService.parse_duration("30m") == 1800
    assert ModerationService.parse_duration("1h") == 3600
    assert ModerationService.parse_duration("7d") == 604800


def test_moderation_commands_are_registered():
    from src.cogs.moderation import ModerationCog

    commands = {command.name for command in ModerationCog.__cog_app_commands__}
    assert commands == {
        "warn",
        "unwarn",
        "warnings",
        "ban",
        "unban",
        "kick",
        "timeout",
        "untimeout",
        "mute",
        "unmute",
        "purge",
        "note",
        "notes",
        "history",
        "case",
    }


@pytest.mark.asyncio
async def test_rbac_or_native_permission_is_supported(monkeypatch):
    from src.middlewares.rbac_check import check_permission

    permissions = SimpleNamespace(ban_members=False, administrator=False)
    user = SimpleNamespace(id=5, roles=[], guild_permissions=permissions)
    guild = SimpleNamespace(owner_id=99, id=1)
    interaction = SimpleNamespace(guild=guild, user=user)
    monkeypatch.setattr(
        "src.middlewares.rbac_check.RBACService.has_permission", lambda *args: _true()
    )

    assert await check_permission(interaction, "ban", "ban_members") is True


async def _true():
    return True
