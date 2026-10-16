import hashlib
import re
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from time import monotonic

from src.dtos.payloads import SpamEventDTO
from src.models.domain import AutoModRule


@dataclass
class _Window:
    events: deque = field(default_factory=deque)
    seen: set = field(default_factory=set)
    total: int = 0
    expires_at: float = 0
    cooldown_until: float = 0


class AntiAbuseService:
    MAX_WINDOWS = 10000
    MAX_EVENTS_PER_WINDOW = 1000
    _windows: OrderedDict[tuple, _Window] = OrderedDict()

    @classmethod
    def cleanup(cls):
        now = monotonic()
        for key, state in list(cls._windows.items()):
            if max(state.expires_at, state.cooldown_until) <= now:
                cls._windows.pop(key, None)

    @classmethod
    async def track_spam(
        cls,
        dto: SpamEventDTO,
        threshold: int,
        window_sec: int,
        rule: str = "spam",
        cooldown_sec: int | None = None,
    ) -> bool:
        if not 1 <= threshold <= cls.MAX_EVENTS_PER_WINDOW or window_sec < 1 or dto.weight < 1:
            raise ValueError("Positive limits required; maximum threshold is 1000.")
        # No await in this update: all shards share this event loop, so expiry,
        # score and cooldown change together in the same event-loop turn.
        key = (dto.guild_id, dto.user_id, rule)
        now = monotonic()
        state = cls._windows.setdefault(key, _Window())
        cls._windows.move_to_end(key)
        while len(cls._windows) > cls.MAX_WINDOWS:
            cls._windows.popitem(last=False)
        if state.cooldown_until > now:
            return False
        while state.events and state.events[0][0] <= now - window_sec:
            _, weight, message_id = state.events.popleft()
            state.total -= weight
            state.seen.discard(message_id)
        if dto.message_id in state.seen:
            return False
        state.events.append((now, dto.weight, dto.message_id))
        state.seen.add(dto.message_id)
        state.total += dto.weight
        state.expires_at = now + window_sec
        if state.total >= threshold:
            state.events.clear()
            state.seen.clear()
            state.total = 0
            state.cooldown_until = now + (cooldown_sec or window_sec)
            return True
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
