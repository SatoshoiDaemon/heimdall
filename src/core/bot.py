import asyncio
import logging

import discord
from discord.ext import commands

from src.core.database import Database
from src.core.event_bus import EventBus
from src.core.exceptions import ModBotException
from src.core.metrics import snapshot
from src.services.anti_abuse_service import AntiAbuseService
from src.services.cache_service import CacheService
from src.services.log_service import LogService
from src.services.moderation_service import ModerationService
from src.utils.embeds import format_error

log = logging.getLogger("modbot.bot")


class ModBot(commands.AutoShardedBot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True

        self._close_lock = asyncio.Lock()
        self._shutdown_done = False
        self.failure = None
        super().__init__(
            command_prefix="!",  # Slash commands primarily used
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self):
        log.info("Running setup hook...")

        # Connect to databases
        await Database.connect()

        # Load cogs
        cogs = [
            "src.cogs.moderation",
            "src.cogs.events",
            "src.cogs.verification",
            "src.cogs.config_ui",
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                log.info(f"Loaded extension: {cog}")
            except Exception as e:
                log.exception("Essential cog failed: %s", cog)
                raise RuntimeError(f"Essential cog failed: {cog}") from e

        # Register tree commands
        log.info("Syncing slash commands...")
        await self.tree.sync()
        log.info("Slash commands synced globally.")

        # Start background workers
        LogService.reset_queue()
        self._bg_task = asyncio.create_task(LogService.worker(self), name="audit-worker")
        self._maintenance_task = asyncio.create_task(self.maintenance(), name="maintenance")
        self._bg_task.add_done_callback(self._worker_finished)
        self._maintenance_task.add_done_callback(self._worker_finished)

        # Setup tree error handler
        self.tree.on_error = self.on_app_command_error

    def _worker_finished(self, task):
        if task.cancelled() or self._shutdown_done or self.is_closed():
            return
        error = task.exception() or RuntimeError(f"Essential task {task.get_name()} stopped")
        self.failure = error
        log.critical("Essential worker stopped: %s", error)
        asyncio.create_task(self.close())

    async def close(self):
        async with self._close_lock:
            if self._shutdown_done:
                return
            self._shutdown_done = True
            log.info("Shutting down bot...")
            # Stop accepting gateway work before closing workers and Mongo.
            try:
                await super().close()
            finally:
                tasks = [
                    task
                    for task in (
                        getattr(self, "_bg_task", None),
                        getattr(self, "_maintenance_task", None),
                    )
                    if task is not None
                ]
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await EventBus.drain(timeout=10)
                await Database.close()
                CacheService.clear()
                AntiAbuseService._windows.clear()

    async def maintenance(self):
        await self.wait_until_ready()
        while not self.is_closed():
            CacheService.cleanup()
            AntiAbuseService.cleanup()
            if self.is_ready():
                try:
                    await ModerationService.reconcile(self)
                    await ModerationService.expire_timeouts()
                    log.info(
                        "Operational snapshot",
                        extra={"action": "maintenance", "outcome": "ready", "metrics": snapshot()},
                    )
                except Exception:
                    log.exception("Maintenance unavailable; retrying after reconnect")
            await asyncio.sleep(20)

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        log.info(f"Serving {len(self.guilds)} guilds.")

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError
    ):
        if isinstance(error, discord.app_commands.CommandOnCooldown):
            msg = f"Command on cooldown. Try again in {error.retry_after:.1f}s."
            embed = format_error(msg)
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)

        elif isinstance(getattr(error, "original", error), ModBotException):
            original = getattr(error, "original", error)
            embed = format_error(str(original))
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        elif isinstance(error, discord.app_commands.CheckFailure):
            # This would catch our RBACAccessDenied since it inherits custom issues
            embed = format_error(str(error))
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            log.error(f"Unhandled app command error: {error}")
            embed = format_error("An unexpected error occurred.")
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
