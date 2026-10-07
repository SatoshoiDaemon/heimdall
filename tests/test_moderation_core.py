from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
import asyncio

import pytest

from src.core.event_bus import EventBus
from src.dtos.payloads import WarnRequestDTO
from src.models.domain import Case
from src.services.moderation_service import ModerationService


class FakeCaseRepository:
    def __init__(self):
        self.cases = {}
        self.next_numbers = {}
        self.revoked = []

    async def create_case(self, **data):
        number = self.next_numbers.get(data["guild_id"], 0) + 1
        self.next_numbers[data["guild_id"]] = number
        document = {
            "_id": f"case-{data['guild_id']}-{number}",
            "case_number": number,
            "created_at": datetime.now(timezone.utc),
            "active": True,
            "revoked": False,
            **data,
        }
        document["metadata"] = data.get("metadata") or {}
        case = Case(**document)
        self.cases[(case.guild_id, case.case_number)] = case
        return case

    async def get_case(self, guild_id, case_number):
        return self.cases.get((guild_id, case_number))

    async def revoke(self, guild_id, case_number):
        case = self.cases[(guild_id, case_number)]
        case.revoked = True
        case.active = False
        self.revoked.append(case_number)
        return 1

    async def get_latest_active(self, guild_id, target_user_id, action):
        candidates = [
            case
            for case in self.cases.values()
            if case.guild_id == guild_id
            and case.target_user_id == target_user_id
            and case.action == action
            and not case.revoked
        ]
        return max(candidates, key=lambda case: case.case_number, default=None)


class FakeWarningRepository:
    def __init__(self):
        self.documents = []

    async def insert_one(self, document):
        self.documents.append(document)
        return str(len(self.documents))

    async def revoke(self, guild_id, case_number):
        for document in self.documents:
            if document["guild_id"] == guild_id and document["case_number"] == case_number:
                document["revoked"] = True
        return 1

    async def get_user_warns(self, guild_id, user_id):
        return []


@asynccontextmanager
async def no_lock(_key, timeout=10):
    yield


@pytest.fixture
def moderation_fakes(monkeypatch):
    case_repo = FakeCaseRepository()
    warning_repo = FakeWarningRepository()
    monkeypatch.setattr(ModerationService, "case_repo", case_repo)
    monkeypatch.setattr(ModerationService, "warn_repo", warning_repo)
    monkeypatch.setattr("src.services.moderation_service.LockService.get_lock", no_lock)
    return case_repo, warning_repo


@pytest.mark.asyncio
async def test_warn_and_unwarn_create_related_cases(moderation_fakes):
    case_repo, warning_repo = moderation_fakes
    audited = []
    EventBus.subscribe("audit_log", lambda event: audited.append(event))

    warning = await ModerationService.issue_warn(WarnRequestDTO(1, 10, 20, "Spam"))
    reversal = await ModerationService.unwarn(1, 20, warning.case_number, "Cleared")
    await asyncio.sleep(0)

    assert warning.action == "WARN"
    assert reversal.action == "UNWARN"
    assert reversal.related_case_number == warning.case_number
    assert case_repo.cases[(1, warning.case_number)].revoked is True
    assert warning_repo.documents[0]["revoked"] is True
    assert len(audited) == 2


def test_duration_parser_supports_human_units():
    assert ModerationService.parse_duration("30m") == 1800
    assert ModerationService.parse_duration("1h") == 3600
    assert ModerationService.parse_duration("7d") == 604800


def test_moderation_commands_are_registered():
    from src.cogs.moderation import ModerationCog

    commands = {command.name for command in ModerationCog.__cog_app_commands__}
    assert commands == {
        "warn", "unwarn", "warnings", "ban", "unban", "kick", "timeout",
        "untimeout", "mute", "unmute", "purge", "note", "notes", "history", "case",
    }


@pytest.mark.asyncio
async def test_rbac_or_native_permission_is_supported(monkeypatch):
    from src.middlewares.rbac_check import check_permission

    permissions = SimpleNamespace(ban_members=False, administrator=False)
    user = SimpleNamespace(id=5, roles=[], guild_permissions=permissions)
    guild = SimpleNamespace(owner_id=99, id=1)
    interaction = SimpleNamespace(guild=guild, user=user)
    monkeypatch.setattr("src.middlewares.rbac_check.RBACService.has_permission", lambda *args: _true())

    assert await check_permission(interaction, "ban", "ban_members") is True


async def _true():
    return True
