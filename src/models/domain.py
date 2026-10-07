from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

# Base Models to map MongoDB documents

class Warn(BaseModel):
    id: str = Field(alias="_id")
    guild_id: int
    user_id: int
    moderator_id: int
    reason: str
    created_at: datetime
    
class Note(BaseModel):
    id: str = Field(alias="_id")
    guild_id: int
    user_id: int
    moderator_id: int
    note: str
    created_at: datetime
    
class Punishment(BaseModel):
    id: str = Field(alias="_id")
    guild_id: int
    user_id: int
    moderator_id: int
    type: str # "ban", "timeout", "mute"
    reason: str
    active: bool = True
    expires_at: Optional[datetime] = None
    created_at: datetime

class GuildConfig(BaseModel):
    id: str = Field(alias="_id")
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

class RolePermission(BaseModel):
    id: str = Field(alias="_id")
    guild_id: int
    role_id: int
    # List of allowed command names or module identifiers (e.g. "ban", "warn", "config")
    allowed_commands: List[str] = []
    
class UserPermission(BaseModel):
    id: str = Field(alias="_id")
    guild_id: int
    user_id: int
    allowed_commands: List[str] = []
