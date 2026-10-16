from dataclasses import dataclass

# Data Transfer Objects used internally across services


@dataclass
class PunishRequestDTO:
    guild_id: int
    user_id: int
    moderator_id: int
    reason: str
    duration_seconds: int | None = None


@dataclass
class WarnRequestDTO:
    guild_id: int
    user_id: int
    moderator_id: int
    reason: str


@dataclass
class NoteRequestDTO:
    guild_id: int
    user_id: int
    moderator_id: int
    note_text: str


@dataclass
class SpamEventDTO:
    guild_id: int
    user_id: int
    message_id: int
    channel_id: int
    content: str
    weight: int = 1


@dataclass
class LogEventDTO:
    guild_id: int
    event_type: str
    description: str
    color: int
    moderator_id: int | None = None
    user_id: int | None = None
    case_number: int | None = None
    metadata: dict | None = None
