import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

import discord

from src.core.database import Database
from src.core.exceptions import (
    CaseNotFound,
    InvalidCase,
    InvalidDuration,
    InvalidTarget,
    ModerationError,
)
from src.core.metrics import counters
from src.dtos.payloads import LogEventDTO, NoteRequestDTO, WarnRequestDTO
from src.models.domain import Case
from src.repositories.bot_repos import (
    CaseRepository,
    NoteRepository,
    PunishmentRepository,
    WarnRepository,
)
from src.services.lock_service import LockService

log = logging.getLogger("modbot.moderation")


class ModerationService:
    """Cases are durable intents; completed cases are the source of truth."""

    case_repo = CaseRepository()
    warn_repo = WarnRepository()
    punish_repo = PunishmentRepository()
    note_repo = NoteRepository()
    DURATION_PATTERN = re.compile(r"^(?P<amount>[1-9]\d*)\s*(?P<unit>[smhd])$", re.IGNORECASE)
    MAX_TIMEOUT_SECONDS = 28 * 86400

    @classmethod
    def parse_duration(cls, value: str) -> int:
        match = cls.DURATION_PATTERN.fullmatch(value.strip())
        if not match:
            raise InvalidDuration("Use a duration such as 30m, 1h or 7d.")
        seconds = (
            int(match["amount"]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match["unit"].lower()]
        )
        if seconds > cls.MAX_TIMEOUT_SECONDS:
            raise InvalidDuration("Timeout cannot exceed 28 days.")
        return seconds

    @staticmethod
    def _reason(reason: str) -> str:
        if not reason.strip():
            raise ModerationError("A reason is required.")
        return reason.strip()[:512]

    @staticmethod
    def _ensure_member_target(guild, target, moderator_id, permission=None, timeout=False):
        bot = guild.me
        moderator = guild.get_member(moderator_id)
        if bot is None or moderator is None:
            raise ModerationError("Moderator or bot is unavailable in this guild.")
        if target.id in {moderator_id, guild.owner_id, bot.id}:
            raise InvalidTarget("Cannot moderate yourself, Heimdall or the guild owner.")
        if bot.top_role <= target.top_role:
            raise InvalidTarget("Heimdall's role must be above the target.")
        # Administrator grants commands, never a bypass of role hierarchy.
        if moderator_id != guild.owner_id and moderator.top_role <= target.top_role:
            raise InvalidTarget("Your role must be above the target, including with RBAC grants.")
        if timeout and target.guild_permissions.administrator:
            raise InvalidTarget("Discord does not allow timeouts of administrators.")
        if permission and not getattr(bot.guild_permissions, permission, False):
            raise ModerationError(f"Heimdall requires {permission}.")

    @staticmethod
    async def _authorize(guild, moderator_id, command, native):
        from src.services.rbac_service import RBACService

        member = guild.get_member(moderator_id)
        if member is None:
            raise ModerationError("Moderator is unavailable.")
        if moderator_id == guild.owner_id or member.guild_permissions.administrator:
            return
        if getattr(member.guild_permissions, native, False):
            return
        if not await RBACService.has_permission(
            guild.id, member.id, [r.id for r in member.roles], command
        ):
            raise ModerationError("Moderator lacks permission for this action.")

    @classmethod
    async def _prepare(cls, *, operation_id=None, origin="manual", **data):
        if operation_id:
            previous = await cls.case_repo.find_one({"operation_id": operation_id})
            if previous:
                return Case(**previous)
        return await cls.case_repo.create_case(
            **data,
            status="pending",
            origin=origin,
            operation_id=operation_id or uuid.uuid4().hex,
        )

    @classmethod
    async def _project(cls, case):
        """Idempotent projections, also repaired after standalone Mongo failures."""
        key = {"guild_id": case.guild_id, "case_number": case.case_number}
        common = {
            **key,
            "user_id": case.target_user_id,
            "moderator_id": case.moderator_id,
            "reason": case.reason,
            "created_at": case.created_at,
        }
        if case.action == "WARN":
            await cls.warn_repo.update_one(
                key, {"$setOnInsert": {**common, "revoked": False}}, upsert=True
            )
        elif case.action == "NOTE":
            await cls.note_repo.update_one(
                key, {"$setOnInsert": {**common, "note": case.reason}}, upsert=True
            )
        elif case.action == "TIMEOUT":
            await cls.punish_repo.update_one(
                key,
                {
                    "$setOnInsert": {
                        **common,
                        "type": "timeout",
                        "active": True,
                        "expires_at": datetime.fromisoformat(case.metadata["until"]),
                    }
                },
                upsert=True,
            )
        if case.related_case_number:
            await cls.case_repo.revoke(case.guild_id, case.related_case_number)
            if case.action == "UNWARN":
                await cls.warn_repo.revoke(case.guild_id, case.related_case_number)
            elif case.action == "UNTIMEOUT":
                await cls.punish_repo.mark_inactive_by_case(case.guild_id, case.related_case_number)

    @classmethod
    async def _finish(cls, case):
        from src.services.log_service import LogService

        async with Database.transaction():
            await cls._project(case)
            await LogService.enqueue_log(
                LogEventDTO(
                    guild_id=case.guild_id,
                    event_type=f"Case #{case.case_number} — {case.action}",
                    description=f"Target: <@{case.target_user_id}> | Moderator: <@{case.moderator_id}>\n{case.reason}",
                    color=0xE67E22,
                    moderator_id=case.moderator_id,
                    user_id=case.target_user_id,
                    case_number=case.case_number,
                    metadata={"origin": case.origin, "operation_id": case.operation_id},
                ),
                event_id=f"case:{case.guild_id}:{case.case_number}",
            )
            await cls.case_repo.update_one(
                {"guild_id": case.guild_id, "case_number": case.case_number},
                {
                    "$set": {
                        "status": "completed",
                        "error": None,
                        "active": case.action in {"WARN", "BAN", "TIMEOUT"},
                    }
                },
            )
        case.status = "completed"
        counters["case_completed"] += 1
        log.info(
            "Moderation case completed",
            extra={
                "guild_id": case.guild_id,
                "case_id": case.case_number,
                "action": case.action,
                "outcome": "completed",
                "duration_seconds": (
                    datetime.now(UTC) - case.created_at.replace(tzinfo=UTC)
                ).total_seconds(),
            },
        )
        return case

    @classmethod
    async def _apply(cls, case, guild=None, channel=None):
        if case.status == "completed":
            return case
        if case.status == "applied":
            return await cls._finish(case)
        if case.status in {"failed", "uncertain"}:
            raise ModerationError(
                f"Operation #{case.case_number} is {case.status}; review the case before retrying."
            )
        external = case.action in {
            "BAN",
            "UNBAN",
            "KICK",
            "TIMEOUT",
            "UNTIMEOUT",
            "PURGE",
            "DELETE",
        }
        if external:
            await cls.case_repo.update_one(
                {"operation_id": case.operation_id}, {"$set": {"status": "applying"}}
            )
            try:
                target = guild.get_member(case.target_user_id) if case.target_user_id else None
                reason = f"Heimdall #{case.case_number}: {case.reason}"[:512]
                if case.action == "BAN":
                    # Ban is idempotent but deleting history is performed only once.
                    try:
                        await guild.fetch_ban(discord.Object(id=case.target_user_id))
                    except discord.NotFound:
                        await guild.ban(
                            discord.Object(id=case.target_user_id),
                            reason=reason,
                            delete_message_seconds=case.metadata.get("delete_message_seconds", 0),
                        )
                elif case.action == "UNBAN":
                    try:
                        await guild.unban(discord.Object(id=case.target_user_id), reason=reason)
                    except discord.NotFound:
                        pass
                elif case.action in {"TIMEOUT", "UNTIMEOUT"}:
                    if target is None:
                        raise ModerationError("Target left the guild; operation requires review.")
                    until = (
                        datetime.fromisoformat(case.metadata["until"])
                        if case.action == "TIMEOUT"
                        else None
                    )
                    await target.timeout(until, reason=reason)
                elif case.action == "KICK":
                    if target is not None:
                        await guild.kick(target, reason=reason)
                elif case.action == "PURGE":
                    deleted = await channel.purge(limit=case.amount, reason=reason)
                    case.amount = len(deleted)
                    await cls.case_repo.update_one(
                        {"operation_id": case.operation_id}, {"$set": {"amount": case.amount}}
                    )
                elif case.action == "DELETE":
                    try:
                        await channel.get_partial_message(case.metadata["message_id"]).delete()
                    except discord.NotFound:
                        pass
            except discord.Forbidden as error:
                await cls.case_repo.update_one(
                    {"operation_id": case.operation_id},
                    {"$set": {"status": "failed", "error": str(error)[:500]}},
                )
                raise ModerationError(
                    "Discord denied the action. Check permissions and hierarchy."
                ) from error
            except Exception as error:
                # Network errors may occur AFTER Discord applied the request.
                state = "uncertain" if case.action in {"PURGE", "KICK"} else "applying"
                await cls.case_repo.update_one(
                    {"operation_id": case.operation_id},
                    {"$set": {"status": state, "error": str(error)[:500]}},
                )
                raise
            # Persist external success before projections. Never replay purge/kick
            # once applied; recovery only completes their database writes.
            await cls.case_repo.update_one(
                {"operation_id": case.operation_id}, {"$set": {"status": "applied"}}
            )
        return await cls._finish(case)

    @classmethod
    async def reconcile(cls, bot):
        docs = await cls.case_repo.col.find(
            {"status": {"$in": ["pending", "applying", "applied"]}}
        ).to_list(length=100)
        for doc in docs:
            case = Case(**doc)
            try:
                async with LockService.get_lock(f"lock:user:{case.guild_id}:{case.target_user_id}"):
                    current = await cls.get_case(case.guild_id, case.case_number)
                    if current.status == "completed":
                        continue
                    if current.status == "applied":
                        await cls._finish(current)
                        continue
                    if current.status == "applying" and current.action in {"PURGE", "KICK"}:
                        await cls.case_repo.update_one(
                            {"operation_id": current.operation_id},
                            {
                                "$set": {
                                    "status": "uncertain",
                                    "error": "Interrupted external action; manual review required",
                                }
                            },
                        )
                        continue
                    guild = bot.get_guild(current.guild_id)
                    if guild is None:
                        continue
                    channel = guild.get_channel(current.channel_id) if current.channel_id else None
                    # Recovery cannot use old intent to bypass a changed hierarchy.
                    target = (
                        guild.get_member(current.target_user_id) if current.target_user_id else None
                    )
                    if target and current.action in {
                        "BAN",
                        "KICK",
                        "TIMEOUT",
                        "UNTIMEOUT",
                        "DELETE",
                    }:
                        cls._ensure_member_target(
                            guild, target, current.moderator_id, timeout=current.action == "TIMEOUT"
                        )
                    await cls._apply(current, guild, channel)
            except Exception:
                log.exception(
                    "Case reconciliation failed",
                    extra={"guild_id": case.guild_id, "case_id": case.case_number},
                )

    @classmethod
    async def issue_warn(
        cls,
        dto: WarnRequestDTO,
        command_source="warn",
        operation_id=None,
        origin="manual",
        guild=None,
    ):
        if guild is not None:
            await cls._authorize(guild, dto.moderator_id, "warn", "moderate_members")
            target = guild.get_member(dto.user_id)
            if target is None:
                raise InvalidTarget("Member is unavailable.")
            cls._ensure_member_target(guild, target, dto.moderator_id)
        async with LockService.get_lock(f"lock:user:{dto.guild_id}:{dto.user_id}"):
            case = await cls._prepare(
                guild_id=dto.guild_id,
                action="WARN",
                target_user_id=dto.user_id,
                moderator_id=dto.moderator_id,
                reason=cls._reason(dto.reason),
                command_source=command_source,
                operation_id=operation_id,
                origin=origin,
            )
            return case if case.status == "completed" else await cls._finish(case)

    @classmethod
    async def unwarn(cls, guild_id, moderator_id, case_number, reason, guild=None):
        original = await cls.get_case(guild_id, case_number)
        if guild is not None:
            await cls._authorize(guild, moderator_id, "unwarn", "moderate_members")
            target = guild.get_member(original.target_user_id)
            if target is not None:
                cls._ensure_member_target(guild, target, moderator_id)
        async with LockService.get_lock(f"lock:user:{guild_id}:{original.target_user_id}"):
            existing = await cls.case_repo.find_one(
                {"operation_id": f"revoke:{guild_id}:{case_number}"}
            )
            if existing:
                case = Case(**existing)
                return case if case.status == "completed" else await cls._finish(case)
            await cls._require_case(guild_id, case_number, "WARN")
            case = await cls._prepare(
                guild_id=guild_id,
                action="UNWARN",
                target_user_id=original.target_user_id,
                moderator_id=moderator_id,
                reason=cls._reason(reason),
                command_source="unwarn",
                related_case_number=case_number,
                operation_id=f"revoke:{guild_id}:{case_number}",
            )
            return await cls._finish(case)

    @classmethod
    async def _member_action(
        cls,
        guild,
        target,
        moderator_id,
        action,
        reason,
        command_source=None,
        duration_seconds=None,
        operation_id=None,
        origin="manual",
        **metadata,
    ):
        permission = {
            "BAN": "ban_members",
            "KICK": "kick_members",
            "TIMEOUT": "moderate_members",
            "UNTIMEOUT": "moderate_members",
        }[action]
        await cls._authorize(guild, moderator_id, command_source or action.lower(), permission)
        if not getattr(guild.me.guild_permissions, permission, False):
            raise ModerationError(f"Heimdall requires {permission}.")
        if isinstance(target, discord.Member) or hasattr(target, "top_role"):
            cls._ensure_member_target(guild, target, moderator_id, permission, action == "TIMEOUT")
        elif target.id in {guild.owner_id, moderator_id, guild.me.id}:
            raise InvalidTarget("Invalid moderation target.")
        if action == "TIMEOUT":
            if not duration_seconds or not 1 <= duration_seconds <= cls.MAX_TIMEOUT_SECONDS:
                raise InvalidDuration("Timeout duration must be between 1 second and 28 days.")
            metadata["until"] = (
                datetime.now(UTC) + timedelta(seconds=duration_seconds)
            ).isoformat()
        async with LockService.get_lock(f"lock:user:{guild.id}:{target.id}"):
            related = metadata.pop("related_case_number", None)
            if related:
                existing = await cls.case_repo.find_one({"operation_id": operation_id})
                if existing:
                    return await cls._apply(Case(**existing), guild)
                original = await cls._require_case(guild.id, related, "TIMEOUT")
                latest = await cls.case_repo.get_latest_active(guild.id, target.id, "TIMEOUT")
                if latest is None or latest.case_number != original.case_number:
                    raise InvalidCase("A newer timeout exists; reverse its case instead.")
            case = await cls._prepare(
                guild_id=guild.id,
                action=action,
                target_user_id=target.id,
                moderator_id=moderator_id,
                reason=cls._reason(reason),
                command_source=command_source or action.lower(),
                duration_seconds=duration_seconds,
                metadata=metadata,
                related_case_number=related,
                operation_id=operation_id,
                origin=origin,
            )
            return await cls._apply(case, guild)

    @classmethod
    async def ban(cls, guild, target, moderator_id, reason, delete_message_seconds=0):
        if not 0 <= delete_message_seconds <= 604800:
            raise ModerationError("Delete history must be between 0 and 604800 seconds.")
        return await cls._member_action(
            guild,
            target,
            moderator_id,
            "BAN",
            reason,
            delete_message_seconds=delete_message_seconds,
        )

    @classmethod
    async def kick(cls, guild, target, moderator_id, reason):
        return await cls._member_action(guild, target, moderator_id, "KICK", reason)

    @classmethod
    async def timeout(
        cls,
        guild,
        target,
        moderator_id,
        duration_seconds,
        reason,
        command_source="timeout",
        operation_id=None,
        origin="manual",
    ):
        return await cls._member_action(
            guild,
            target,
            moderator_id,
            "TIMEOUT",
            reason,
            command_source,
            duration_seconds,
            operation_id,
            origin,
        )

    @classmethod
    async def unban(cls, guild, user_id, moderator_id, reason):
        await cls._authorize(guild, moderator_id, "unban", "ban_members")
        async with LockService.get_lock(f"lock:user:{guild.id}:{user_id}"):
            original = await cls.case_repo.get_latest_active(guild.id, user_id, "BAN")
            if original is None:
                # Repeated reversals return their previous completed case.
                previous = await cls.case_repo.col.find_one(
                    {
                        "guild_id": guild.id,
                        "target_user_id": user_id,
                        "action": "UNBAN",
                        "status": "completed",
                    },
                    sort=[("case_number", -1)],
                )
                if previous:
                    return Case(**previous)
                raise InvalidCase("No active ban case found.")
            case = await cls._prepare(
                guild_id=guild.id,
                action="UNBAN",
                target_user_id=user_id,
                moderator_id=moderator_id,
                reason=cls._reason(reason),
                command_source="unban",
                related_case_number=original.case_number,
                operation_id=f"revoke:{guild.id}:{original.case_number}",
            )
            return await cls._apply(case, guild)

    @classmethod
    async def untimeout(cls, guild, target, moderator_id, case_number, reason):
        original = await cls.get_case(guild.id, case_number)
        if original.target_user_id != target.id or original.action != "TIMEOUT":
            raise InvalidTarget("Target does not match a timeout case.")
        return await cls._member_action(
            guild,
            target,
            moderator_id,
            "UNTIMEOUT",
            reason,
            related_case_number=case_number,
            operation_id=f"revoke:{guild.id}:{case_number}",
        )

    @classmethod
    async def mute(cls, *args, **kwargs):
        return await cls.timeout(*args, **kwargs, command_source="mute")

    @classmethod
    async def unmute(cls, *args, **kwargs):
        return await cls.untimeout(*args, **kwargs)

    @classmethod
    async def purge(cls, channel, moderator_id, amount, reason):
        await cls._authorize(channel.guild, moderator_id, "purge", "manage_messages")
        if not channel.permissions_for(channel.guild.me).manage_messages:
            raise ModerationError("Heimdall requires Manage Messages here.")
        if not 1 <= amount <= 100:
            raise ModerationError("Purge amount must be between 1 and 100.")
        async with LockService.get_lock(f"lock:user:{channel.guild.id}:None"):
            case = await cls._prepare(
                guild_id=channel.guild.id,
                action="PURGE",
                target_user_id=None,
                moderator_id=moderator_id,
                reason=cls._reason(reason),
                command_source="purge",
                channel_id=channel.id,
                amount=amount,
            )
            return await cls._apply(case, channel.guild, channel)

    @classmethod
    async def add_note(cls, dto: NoteRequestDTO, guild=None):
        if guild is not None:
            await cls._authorize(guild, dto.moderator_id, "note", "moderate_members")
        async with LockService.get_lock(f"lock:user:{dto.guild_id}:{dto.user_id}"):
            case = await cls._prepare(
                guild_id=dto.guild_id,
                action="NOTE",
                target_user_id=dto.user_id,
                moderator_id=dto.moderator_id,
                reason=cls._reason(dto.note_text),
                command_source="note",
            )
            return await cls._finish(case)

    @classmethod
    async def _require_case(cls, guild_id, case_number, action):
        case = await cls.get_case(guild_id, case_number)
        if case.action != action or case.revoked or case.status != "completed":
            raise InvalidCase("Case cannot be reversed in its current state.")
        return case

    @classmethod
    async def get_case(cls, guild_id, case_number):
        case = await cls.case_repo.get_case(guild_id, case_number)
        if case is None:
            raise CaseNotFound(f"Case #{case_number} was not found.")
        return case

    @classmethod
    async def history(cls, guild_id, target_user_id=None, page=1, **filters):
        if page < 1:
            raise ModerationError("Page must be at least 1.")
        return await cls.case_repo.list_cases(
            guild_id, target_user_id=target_user_id, page=page, **filters
        )

    @classmethod
    async def warnings(cls, guild_id, user_id):
        return await cls.warn_repo.get_user_warns(guild_id, user_id)

    @classmethod
    async def notes(cls, guild_id, user_id):
        return await cls.note_repo.get_user_notes(guild_id, user_id)
