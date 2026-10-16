import logging
import re
import uuid

from redis.exceptions import RedisError

from src.core.redis_client import RedisClient
from src.dtos.payloads import SpamEventDTO
from src.models.domain import AutoModRule

log = logging.getLogger("modbot.automod")

# Per-event weight + unique ID prevents timestamp collisions. Redis TIME avoids
# clock skew across workers. All expiry, calculation and cooldown are atomic.
SCORE_SCRIPT = """
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2])/1000000
local cutoff = now-tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',cutoff)
redis.call('ZADD',KEYS[1],now,ARGV[4]..':'..ARGV[1])
redis.call('EXPIRE',KEYS[1],ARGV[2])
local entries = redis.call('ZRANGE',KEYS[1],0,-1)
local total = 0
for _,v in ipairs(entries) do total=total+tonumber(string.match(v,':(%d+)$')) end
if total >= tonumber(ARGV[3]) then
    redis.call('DEL',KEYS[1])
    if redis.call('SET',KEYS[2],'1','NX','EX',ARGV[5]) then return 1 end
end
return 0
"""


class AntiAbuseService:
    @staticmethod
    async def track_spam(
        dto: SpamEventDTO,
        threshold: int,
        window_sec: int,
        rule: str = "spam",
        cooldown_sec: int | None = None,
    ) -> bool:
        if threshold < 1 or window_sec < 1 or dto.weight < 1:
            raise ValueError("Positive spam limits and weights are required.")
        key = f"spam:{{{dto.guild_id}:{dto.user_id}}}:{rule}"
        try:
            return bool(
                await RedisClient.redis_conn.eval(
                    SCORE_SCRIPT,
                    2,
                    key,
                    key + ":cooldown",
                    dto.weight,
                    window_sec,
                    threshold,
                    uuid.uuid4().hex,
                    cooldown_sec or window_sec,
                )
            )
        except RedisError:
            # Never punish on incomplete rate data; static filters still work.
            log.exception(
                "Rate detector unavailable",
                extra={"guild_id": dto.guild_id, "action": rule, "outcome": "skipped"},
            )
            return False

    @staticmethod
    def rules(config):
        defaults = {
            "spam": AutoModRule(
                enabled=config.anti_spam_enabled,
                threshold=config.spam_threshold_score,
                cooldown_seconds=config.spam_cooldown_seconds,
            ),
            "mentions": AutoModRule(
                enabled=config.anti_mention_enabled,
                action="delete",
                threshold=config.mention_limit_per_msg,
            ),
            "invites": AutoModRule(enabled=config.anti_link_enabled, action="delete"),
        }
        return {**defaults, **config.automod_rules}

    @staticmethod
    async def detect(message, config) -> list[str]:
        if (
            message.channel.id in config.exempt_channel_ids
            or any(role.id in config.exempt_role_ids for role in message.author.roles)
            or message.author.guild_permissions.administrator
        ):
            return []
        rules = AntiAbuseService.rules(config)
        content = message.content.casefold()
        hits = []
        for name, rule in rules.items():
            if not rule.enabled:
                continue
            hit = False
            if name in {"spam", "repeated"}:
                import hashlib

                suffix = (
                    name
                    if name == "spam"
                    else name + ":" + hashlib.sha256(content.encode()).hexdigest()
                )
                dto = SpamEventDTO(
                    message.guild.id,
                    message.author.id,
                    message.id,
                    message.channel.id,
                    message.content,
                    1 + 2 * len(message.mentions) if name == "spam" else 1,
                )
                hit = await AntiAbuseService.track_spam(
                    dto, rule.threshold, config.spam_cooldown_seconds, suffix, rule.cooldown_seconds
                )
            elif name == "mentions":
                hit = (
                    len(message.mentions) + len(message.role_mentions) >= rule.threshold
                    or message.mention_everyone
                )
            elif name == "invites":
                hit = bool(
                    re.search(r"(?:discord\.gg|discord(?:app)?\.com/invite)/[\w-]+", content)
                )
            elif name == "urls":
                hit = bool(re.search(r"https?://\S+", content))
            elif name == "words":
                hit = any(
                    re.search(r"(?<!\w)" + re.escape(word.casefold()) + r"(?!\w)", content)
                    for word in config.blocked_words
                    if word
                )
            if hit:
                hits.append(name)
        return hits
