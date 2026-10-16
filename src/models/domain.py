from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

MongoId = Annotated[str, BeforeValidator(str)]


class DomainModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


# Base Models to map MongoDB documents


class Warn(DomainModel):
    id: MongoId = Field(alias="_id")
    guild_id: int
    user_id: int
    moderator_id: int
    reason: str
    created_at: datetime
    case_number: int | None = None
    revoked: bool = False


class Note(DomainModel):
    id: MongoId = Field(alias="_id")
    guild_id: int
    user_id: int
    moderator_id: int
    note: str
    created_at: datetime
    case_number: int | None = None


class Punishment(DomainModel):
    id: MongoId = Field(alias="_id")
    guild_id: int
    user_id: int
    moderator_id: int
    type: str  # "ban", "timeout", "mute"
    reason: str
    active: bool = True
    expires_at: datetime | None = None
    created_at: datetime
    case_number: int | None = None


class Case(DomainModel):
    id: MongoId = Field(alias="_id")
    case_number: int
    guild_id: int
    action: str
    target_user_id: int | None = None
    moderator_id: int
    reason: str
    duration_seconds: int | None = None
    channel_id: int | None = None
    amount: int | None = None
    created_at: datetime
    active: bool = True
    revoked: bool = False
    related_case_number: int | None = None
    command_source: str | None = None
    status: str = "completed"
    origin: str = "manual"
    operation_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AutoModRule(DomainModel):
    enabled: bool = False
    action: str = Field(default="warn", pattern="^(warn|delete|timeout)$")
    threshold: int = Field(default=3, ge=1, le=1000)
    duration_seconds: int = Field(default=300, ge=1, le=2419200)
    cooldown_seconds: int = Field(default=60, ge=1, le=86400)


class GuildConfig(DomainModel):
    id: MongoId = Field(alias="_id")
    guild_id: int

    # Modules
    anti_spam_enabled: bool = False
    anti_link_enabled: bool = False
    anti_mention_enabled: bool = False

    verified_role_id: int | None = None
    exempt_role_ids: list[int] = Field(default_factory=list)
    exempt_channel_ids: list[int] = Field(default_factory=list)
    blocked_words: list[str] = Field(default_factory=list)
    automod_rules: dict[str, AutoModRule] = Field(default_factory=dict)

    # Thresholds
    spam_threshold_score: int = Field(default=20, ge=1, le=1000)
    spam_cooldown_seconds: int = Field(default=60, ge=1, le=86400)
    mention_limit_per_msg: int = Field(default=5, ge=1, le=100)

    # Log Channels
    log_channel_id: int | None = None
    alert_channel_id: int | None = None


class RolePermission(DomainModel):
    id: MongoId = Field(alias="_id")
    guild_id: int
    role_id: int
    # List of allowed command names or module identifiers (e.g. "ban", "warn", "config")
    allowed_commands: list[str] = Field(default_factory=list)


class UserPermission(DomainModel):
    id: MongoId = Field(alias="_id")
    guild_id: int
    user_id: int
    allowed_commands: list[str] = Field(default_factory=list)
