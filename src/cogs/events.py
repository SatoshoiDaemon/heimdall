import discord
from discord.ext import commands
from src.services.config_service import ConfigService
from src.services.anti_abuse_service import AntiAbuseService
from src.dtos.payloads import SpamEventDTO, LogEventDTO
from src.core.event_bus import EventBus
import re

class EventListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        config = await ConfigService.get_guild_config(message.guild.id)
        
        weight = 1
        # Evaluate abuse settings
        if config.anti_mention_enabled:
            # Check mentions
            if len(message.mentions) > config.mention_limit_per_msg:
                # Immediate punish
                await message.delete()
                # Dummy emit
                EventBus.emit("audit_log", LogEventDTO(
                    guild_id=message.guild.id,
                    event_type="Anti-Mention Triggered",
                    description=f"{message.author.mention} tried to ping {len(message.mentions)} users.",
                    color=0xFF0000,
                    user_id=message.author.id
                ))
                return
            weight += len(message.mentions) * 2

        if config.anti_link_enabled:
            # Simple invite regex
            if re.search(r"discord\.gg/[a-zA-Z0-9]+", message.content):
                await message.delete()
                return

        if config.anti_spam_enabled:
            dto = SpamEventDTO(
                guild_id=message.guild.id,
                user_id=message.author.id,
                message_id=message.id,
                channel_id=message.channel.id,
                content=message.content,
                weight=weight
            )
            is_spam = await AntiAbuseService.track_spam(dto, config.spam_threshold_score, config.spam_cooldown_seconds)
            if is_spam:
                await message.channel.send(f"⚠️ {message.author.mention}, chill out! Stop spamming.", delete_after=5)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
            
        # Emit log
        log_dto = LogEventDTO(
            guild_id=message.guild.id,
            event_type="Message Deleted",
            description=f"Message by {message.author.mention} deleted in {message.channel.mention}.\n**Content:** {message.content}",
            color=0x8A2BE2,
            user_id=message.author.id
        )
        EventBus.emit("audit_log", log_dto)

async def setup(bot):
    await bot.add_cog(EventListener(bot))
