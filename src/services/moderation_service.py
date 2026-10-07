import re
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable

import discord

from src.core.event_bus import EventBus
from src.core.exceptions import CaseNotFound, InvalidCase, InvalidDuration, InvalidTarget, ModerationError
from src.dtos.payloads import LogEventDTO, NoteRequestDTO, WarnRequestDTO
from src.models.domain import Case
from src.repositories.bot_repos import CaseRepository, NoteRepository, PunishmentRepository, WarnRepository
from src.services.lock_service import LockService


class ModerationService:
    """Application service for manual moderation operations."""

    case_repo = CaseRepository()
    warn_repo = WarnRepository()
    punish_repo = PunishmentRepository()
    note_repo = NoteRepository()

    DURATION_PATTERN = re.compile(r"^(?P<amount>[1-9]\d*)\s*(?P<unit>[smhd])$", re.IGNORECASE)
    MAX_TIMEOUT_SECONDS = 28 * 24 * 60 * 60

    @classmethod
    def parse_duration(cls, value: str) -> int:
        match = cls.DURATION_PATTERN.fullmatch(value.strip())
        if not match:
            raise InvalidDuration("Duration must use a format such as `30m`, `1h` or `7d`.")
        multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}[match.group("unit").lower()]
        seconds = int(match.group("amount")) * multiplier
        if seconds > cls.MAX_TIMEOUT_SECONDS:
            raise InvalidDuration("Timeout duration cannot exceed 28 days.")
        return seconds

    @staticmethod
    def _reason(reason: str) -> str:
        normalized = reason.strip()
        if not normalized:
            raise ModerationError("A moderation reason is required.")
        return normalized[:512]

    @staticmethod
    def _ensure_member_target(guild: discord.Guild, target: discord.Member, moderator_id: int) -> None:
        if target.id == moderator_id:
            raise InvalidTarget("You cannot moderate yourself.")
        if target.id == guild.owner_id:
            raise InvalidTarget("The server owner cannot be moderated.")
        bot_member = guild.me
        if bot_member is None:
            raise ModerationError("Heimdall is not available as a guild member.")
        if target.id == bot_member.id:
            raise InvalidTarget("Heimdall cannot moderate itself.")
        if bot_member.top_role <= target.top_role:
            raise InvalidTarget("Heimdall's highest role must be above the target's highest role.")

    @staticmethod
    async def _discord_action(action: Awaitable[Any]) -> Any:
        try:
            return await action
        except discord.Forbidden as error:
            raise ModerationError("Discord denied this action. Check Heimdall's permissions and role hierarchy.") from error
        except discord.NotFound as error:
            raise ModerationError("The Discord target or resource no longer exists.") from error
        except discord.HTTPException as error:
            raise ModerationError("Discord rejected the action. Please try again later.") from error

    @classmethod
    async def _create_case(
        cls,
        *,
        guild_id: int,
        action: str,
        target_user_id: int | None,
        moderator_id: int,
        reason: str,
        command_source: str,
        duration_seconds: int | None = None,
        channel_id: int | None = None,
        amount: int | None = None,
        related_case_number: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Case:
        case = await cls.case_repo.create_case(
            guild_id=guild_id,
            action=action,
            target_user_id=target_user_id,
            moderator_id=moderator_id,
            reason=reason,
            duration_seconds=duration_seconds,
            channel_id=channel_id,
            amount=amount,
            related_case_number=related_case_number,
            command_source=command_source,
            metadata=metadata,
        )
        target_label = f"<@{target_user_id}>" if target_user_id else "the current channel"
        EventBus.emit(
            "audit_log",
            LogEventDTO(
                guild_id=guild_id,
                event_type=f"Case #{case.case_number} — {action}",
                description=f"{target_label} moderated by <@{moderator_id}>.\n**Reason:** {reason}",
                color=0xE67E22,
                moderator_id=moderator_id,
                user_id=target_user_id,
                case_number=case.case_number,
                metadata=metadata,
            ),
        )
        return case

    @classmethod
    async def issue_warn(cls, dto: WarnRequestDTO, command_source: str = "warn") -> Case:
        reason = cls._reason(dto.reason)
        async with LockService.get_lock(f"lock:user:{dto.guild_id}:{dto.user_id}"):
            case = await cls._create_case(
                guild_id=dto.guild_id,
                action="WARN",
                target_user_id=dto.user_id,
                moderator_id=dto.moderator_id,
                reason=reason,
                command_source=command_source,
            )
            await cls.warn_repo.insert_one(
                {
                    "guild_id": dto.guild_id,
                    "user_id": dto.user_id,
                    "moderator_id": dto.moderator_id,
                    "reason": reason,
                    "created_at": datetime.now(timezone.utc),
                    "case_number": case.case_number,
                    "revoked": False,
                }
            )
            return case

    @classmethod
    async def unwarn(cls, guild_id: int, moderator_id: int, case_number: int, reason: str) -> Case:
        original = await cls._require_case(guild_id, case_number, "WARN")
        async with LockService.get_lock(f"lock:user:{guild_id}:{original.target_user_id}"):
            reversal = await cls._create_case(
                guild_id=guild_id,
                action="UNWARN",
                target_user_id=original.target_user_id,
                moderator_id=moderator_id,
                reason=cls._reason(reason),
                command_source="unwarn",
                related_case_number=case_number,
            )
            await cls.case_repo.revoke(guild_id, case_number)
            await cls.warn_repo.revoke(guild_id, case_number)
            return reversal

    @classmethod
    async def ban(
        cls,
        guild: discord.Guild,
        target: discord.Member | discord.User,
        moderator_id: int,
        reason: str,
        delete_message_seconds: int = 0,
    ) -> Case:
        reason = cls._reason(reason)
        if isinstance(target, discord.Member):
            cls._ensure_member_target(guild, target, moderator_id)
        if not 0 <= delete_message_seconds <= 604800:
            raise ModerationError("Deleted message duration must be between 0 and 604800 seconds.")
        async with LockService.get_lock(f"lock:user:{guild.id}:{target.id}"):
            await cls._discord_action(
                guild.ban(target, reason=reason, delete_message_seconds=delete_message_seconds)
            )
            return await cls._create_case(
                guild_id=guild.id,
                action="BAN",
                target_user_id=target.id,
                moderator_id=moderator_id,
                reason=reason,
                command_source="ban",
                metadata={"delete_message_seconds": delete_message_seconds},
            )

    @classmethod
    async def unban(cls, guild: discord.Guild, user_id: int, moderator_id: int, reason: str) -> Case:
        original = await cls.case_repo.get_latest_active(guild.id, user_id, "BAN")
        if original is None:
            raise InvalidCase("No active ban case was found for this user.")
        reason = cls._reason(reason)
        async with LockService.get_lock(f"lock:user:{guild.id}:{user_id}"):
            await cls._discord_action(guild.unban(discord.Object(id=user_id), reason=reason))
            reversal = await cls._create_case(
                guild_id=guild.id,
                action="UNBAN",
                target_user_id=user_id,
                moderator_id=moderator_id,
                reason=reason,
                command_source="unban",
                related_case_number=original.case_number,
            )
            await cls.case_repo.revoke(guild.id, original.case_number)
            return reversal

    @classmethod
    async def kick(cls, guild: discord.Guild, target: discord.Member, moderator_id: int, reason: str) -> Case:
        reason = cls._reason(reason)
        cls._ensure_member_target(guild, target, moderator_id)
        async with LockService.get_lock(f"lock:user:{guild.id}:{target.id}"):
            await cls._discord_action(guild.kick(target, reason=reason))
            return await cls._create_case(
                guild_id=guild.id,
                action="KICK",
                target_user_id=target.id,
                moderator_id=moderator_id,
                reason=reason,
                command_source="kick",
            )

    @classmethod
    async def timeout(
        cls,
        guild: discord.Guild,
        target: discord.Member,
        moderator_id: int,
        duration_seconds: int,
        reason: str,
        command_source: str = "timeout",
    ) -> Case:
        reason = cls._reason(reason)
        cls._ensure_member_target(guild, target, moderator_id)
        if not 1 <= duration_seconds <= cls.MAX_TIMEOUT_SECONDS:
            raise InvalidDuration("Timeout duration must be between 1 second and 28 days.")
        async with LockService.get_lock(f"lock:user:{guild.id}:{target.id}"):
            until = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
            await cls._discord_action(target.timeout(until, reason=reason))
            case = await cls._create_case(
                guild_id=guild.id,
                action="TIMEOUT",
                target_user_id=target.id,
                moderator_id=moderator_id,
                reason=reason,
                duration_seconds=duration_seconds,
                command_source=command_source,
            )
            await cls.punish_repo.insert_one(
                {
                    "guild_id": guild.id,
                    "user_id": target.id,
                    "moderator_id": moderator_id,
                    "type": "timeout",
                    "reason": reason,
                    "active": True,
                    "expires_at": until,
                    "created_at": datetime.now(timezone.utc),
                    "case_number": case.case_number,
                }
            )
            return case

    @classmethod
    async def untimeout(cls, guild: discord.Guild, target: discord.Member, moderator_id: int, case_number: int, reason: str) -> Case:
        original = await cls._require_case(guild.id, case_number, "TIMEOUT")
        if original.target_user_id != target.id:
            raise InvalidTarget("The selected member does not match the timeout case.")
        cls._ensure_member_target(guild, target, moderator_id)
        reason = cls._reason(reason)
        async with LockService.get_lock(f"lock:user:{guild.id}:{target.id}"):
            await cls._discord_action(target.timeout(None, reason=reason))
            reversal = await cls._create_case(
                guild_id=guild.id,
                action="UNTIMEOUT",
                target_user_id=target.id,
                moderator_id=moderator_id,
                reason=reason,
                command_source="untimeout",
                related_case_number=case_number,
            )
            await cls.case_repo.revoke(guild.id, original.case_number)
            await cls.punish_repo.mark_inactive_by_case(guild.id, original.case_number)
            return reversal

    @classmethod
    async def mute(cls, *args, **kwargs) -> Case:
        kwargs["command_source"] = "mute"
        return await cls.timeout(*args, **kwargs)

    @classmethod
    async def unmute(cls, *args, **kwargs) -> Case:
        return await cls.untimeout(*args, **kwargs)

    @classmethod
    async def purge(cls, channel: discord.TextChannel, moderator_id: int, amount: int, reason: str) -> Case:
        if not 1 <= amount <= 100:
            raise ModerationError("Purge amount must be between 1 and 100 messages.")
        reason = cls._reason(reason)
        deleted = await cls._discord_action(channel.purge(limit=amount, reason=reason))
        return await cls._create_case(
            guild_id=channel.guild.id,
            action="PURGE",
            target_user_id=None,
            moderator_id=moderator_id,
            reason=reason,
            command_source="purge",
            channel_id=channel.id,
            amount=len(deleted),
        )

    @classmethod
    async def add_note(cls, dto: NoteRequestDTO) -> Case:
        note = cls._reason(dto.note_text)
        case = await cls._create_case(
            guild_id=dto.guild_id,
            action="NOTE",
            target_user_id=dto.user_id,
            moderator_id=dto.moderator_id,
            reason=note,
            command_source="note",
        )
        await cls.note_repo.insert_one(
            {
                "guild_id": dto.guild_id,
                "user_id": dto.user_id,
                "moderator_id": dto.moderator_id,
                "note": note,
                "created_at": datetime.now(timezone.utc),
                "case_number": case.case_number,
            }
        )
        return case

    @classmethod
    async def _require_case(cls, guild_id: int, case_number: int, action: str) -> Case:
        case = await cls.case_repo.get_case(guild_id, case_number)
        if case is None:
            raise CaseNotFound(f"Case #{case_number} was not found.")
        if case.action != action:
            raise InvalidCase(f"Case #{case_number} is not a {action} case.")
        if case.revoked:
            raise InvalidCase(f"Case #{case_number} has already been revoked.")
        return case

    @classmethod
    async def get_case(cls, guild_id: int, case_number: int) -> Case:
        case = await cls.case_repo.get_case(guild_id, case_number)
        if case is None:
            raise CaseNotFound(f"Case #{case_number} was not found.")
        return case

    @classmethod
    async def history(cls, guild_id: int, target_user_id: int | None = None, page: int = 1) -> list[Case]:
        if page < 1:
            raise ModerationError("Page must be at least 1.")
        return await cls.case_repo.list_cases(guild_id, target_user_id=target_user_id, page=page)

    @classmethod
    async def warnings(cls, guild_id: int, user_id: int) -> list:
        return await cls.warn_repo.get_user_warns(guild_id, user_id)

    @classmethod
    async def notes(cls, guild_id: int, user_id: int) -> list:
        return await cls.note_repo.get_user_notes(guild_id, user_id)
