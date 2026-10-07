from datetime import datetime
from typing import Annotated, Any, Optional

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
    case_number: Optional[int] = None
    revoked: bool = False
    
class Note(DomainModel):
    id: MongoId = Field(alias="_id")
    guild_id: int
    user_id: int
    moderator_id: int
    note: str
    created_at: datetime
    case_number: Optional[int] = None
    
class Punishment(DomainModel):
    id: MongoId = Field(alias="_id")
    guild_id: int
    user_id: int
    moderator_id: int
    type: str # "ban", "timeout", "mute"
    reason: str
    active: bool = True
    expires_at: Optional[datetime] = None
    created_at: datetime
    case_number: Optional[int] = None


class Case(DomainModel):
    id: MongoId = Field(alias="_id")
    case_number: int
    guild_id: int
    action: str
    target_user_id: Optional[int] = None
    moderator_id: int
    reason: str
    duration_seconds: Optional[int] = None
    channel_id: Optional[int] = None
    amount: Optional[int] = None
    created_at: datetime
    active: bool = True
    revoked: bool = False
    related_case_number: Optional[int] = None
    command_source: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class GuildConfig(DomainModel):
    id: MongoId = Field(alias="_id")
    guild_id: int
    
    # Modules
    anti_spam_enabled: bool = False
    anti_link_enabled: bool = False
    anti_mention_enabled: bool = False
    
    # Thresholds
    spam_threshold_score: int = 20
    spam_cooldown_seconds: int = 60
    mention_limit_per_msg: int = 5
    
    # Log Channels
    log_channel_id: Optional[int] = None
    alert_channel_id: Optional[int] = None

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
