from src.core.redis_client import RedisClient
from src.dtos.payloads import WarnRequestDTO
from src.models.domain import AutoModRule, Case
from src.services.anti_abuse_service import AntiAbuseService
from src.services.config_service import ConfigService
from src.services.lock_service import LockService
from src.services.moderation_service import ModerationService


class AutoModService:
    @staticmethod
    async def consume(message, rule_name):
        config = await ConfigService.get_guild_config(message.guild.id)
        rule = AntiAbuseService.rules(config).get(rule_name, AutoModRule())
        if not rule.enabled or message.channel.id in config.exempt_channel_ids:
            return None
        if (
            any(r.id in config.exempt_role_ids for r in message.author.roles)
            or message.author.guild_permissions.administrator
        ):
            return None
        guild = message.guild
        actor = guild.me.id
        ModerationService._ensure_member_target(
            guild,
            message.author,
            actor if actor != message.author.id else -1,
            "moderate_members" if rule.action == "timeout" else None,
            rule.action == "timeout",
        )
        operation_id = f"automod:{guild.id}:{message.id}:{rule_name}"
        reason = f"AutoMod: {rule_name}"
        # Lock and persisted operation ID suppress delivery duplicates. Cooldown is
        # per member/rule, independent of message ID, and set only after success.
        async with LockService.get_lock(f"lock:automod:{guild.id}:{message.author.id}:{rule_name}"):
            previous = await ModerationService.case_repo.find_one({"operation_id": operation_id})
            if previous:
                return Case(**previous)
            key = f"automod:cooldown:{guild.id}:{message.author.id}:{rule_name}"
            if await RedisClient.redis_conn.get(key):
                return None
            if rule.action == "warn":
                case = await ModerationService.issue_warn(
                    WarnRequestDTO(guild.id, message.author.id, actor, reason),
                    command_source=f"automod:{rule_name}",
                    origin="automatic",
                    operation_id=operation_id,
                    guild=guild,
                )
            elif rule.action == "timeout":
                case = await ModerationService.timeout(
                    guild,
                    message.author,
                    actor,
                    rule.duration_seconds,
                    reason,
                    command_source=f"automod:{rule_name}",
                    operation_id=operation_id,
                    origin="automatic",
                )
            else:
                if not message.channel.permissions_for(guild.me).manage_messages:
                    from src.core.exceptions import ModerationError

                    raise ModerationError("Heimdall requires Manage Messages for AutoMod deletion.")
                async with LockService.get_lock(f"lock:user:{guild.id}:{message.author.id}"):
                    case = await ModerationService._prepare(
                        guild_id=guild.id,
                        action="DELETE",
                        target_user_id=message.author.id,
                        moderator_id=actor,
                        reason=reason,
                        command_source=f"automod:{rule_name}",
                        origin="automatic",
                        operation_id=operation_id,
                        channel_id=message.channel.id,
                        metadata={"message_id": message.id},
                    )
                    case = await ModerationService._apply(case, guild, message.channel)
            await RedisClient.redis_conn.set(key, "1", ex=rule.cooldown_seconds)
            return case
