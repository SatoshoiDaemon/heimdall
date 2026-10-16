import logging

import discord
from discord.ext import commands

from src.core.event_bus import EventBus
from src.dtos.payloads import LogEventDTO
from src.services.anti_abuse_service import AntiAbuseService
from src.services.automod_service import AutoModService
from src.services.config_service import ConfigService

log = logging.getLogger("modbot.events")


class EventListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        EventBus.subscribe("automod_detected", AutoModService.consume)

    async def cog_unload(self):
        EventBus.unsubscribe("automod_detected", AutoModService.consume)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        try:
            config = await ConfigService.get_guild_config(message.guild.id)
            for rule in await AntiAbuseService.detect(message, config):
                await EventBus.publish("automod_detected", message, rule)
        except Exception:
            log.exception(
                "AutoMod processing failed",
                extra={"guild_id": message.guild.id, "action": "automod", "outcome": "failed"},
            )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        await EventBus.publish(
            "audit_log",
            LogEventDTO(
                guild_id=message.guild.id,
                event_type="Message Deleted",
                description=f"Message by {message.author.mention} in {message.channel.mention}.\n{message.content}",
                color=0x8A2BE2,
                user_id=message.author.id,
            ),
        )


async def setup(bot):
    await bot.add_cog(EventListener(bot))
