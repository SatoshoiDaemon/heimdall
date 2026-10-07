import datetime
import discord
from src.repositories.bot_repos import WarnRepository, PunishmentRepository, NoteRepository
from src.services.lock_service import LockService
from src.dtos.payloads import PunishRequestDTO, WarnRequestDTO, NoteRequestDTO, LogEventDTO
from src.core.event_bus import EventBus
from src.core.exceptions import ModBotException

class ModerationService:
    warn_repo = WarnRepository()
    punish_repo = PunishmentRepository()  # Assuming defined correctly
    note_repo = NoteRepository()

    @classmethod
    async def issue_warn(cls, dto: WarnRequestDTO) -> int:
        lock_key = f"lock:user:{dto.guild_id}:{dto.user_id}"
        
        async with LockService.get_lock(lock_key):
            # Insert warn
            warn_doc = {
                "guild_id": dto.guild_id,
                "user_id": dto.user_id,
                "moderator_id": dto.moderator_id,
                "reason": dto.reason,
                "created_at": datetime.datetime.utcnow()
            }
            await cls.warn_repo.insert_one(warn_doc)
            
            # Fetch total warns to trigger potential punishments
            warns = await cls.warn_repo.get_user_warns(dto.guild_id, dto.user_id)
            total_warns = len(warns)
            
            # Emit Log
            log_dto = LogEventDTO(
                guild_id=dto.guild_id,
                event_type="User Warned",
                description=f"<@{dto.user_id}> was warned.\n**Reason:** {dto.reason}\n**Total Warns:** {total_warns}",
                color=0xFFA500,
                moderator_id=dto.moderator_id,
                user_id=dto.user_id
            )
            EventBus.emit("audit_log", log_dto)
            
            return total_warns

    @classmethod
    async def add_note(cls, dto: NoteRequestDTO):
        doc = {
            "guild_id": dto.guild_id,
            "user_id": dto.user_id,
            "moderator_id": dto.moderator_id,
            "note": dto.note_text,
            "created_at": datetime.datetime.utcnow()
        }
        await cls.note_repo.insert_one(doc)
