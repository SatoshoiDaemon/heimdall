import asyncio
import json
import logging
from contextlib import suppress
from pathlib import Path
from time import time

import discord
from discord.ext import commands

from src.core.database import Database
from src.core.event_bus import EventBus
from src.core.exceptions import ModBotException
from src.core.metrics import snapshot
from src.core.redis_client import RedisClient
from src.services.log_service import LogService
from src.services.moderation_service import ModerationService
from src.utils.embeds import format_error

log = logging.getLogger("modbot.bot")


class ModBot(commands.AutoShardedBot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True

        super().__init__(
            command_prefix="!",  # Slash commands primarily used
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self):
        log.info("Running setup hook...")

        # Connect to databases
        await Database.connect()
        await RedisClient.connect()

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
        self._bg_task = asyncio.create_task(LogService.worker(self))
        self._maintenance_task = asyncio.create_task(self.maintenance())

        # Setup tree error handler
        self.tree.on_error = self.on_app_command_error

    async def close(self):
        log.info("Shutting down bot...")
        if hasattr(self, "_bg_task"):
            self._bg_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._bg_task
        if hasattr(self, "_maintenance_task"):
            self._maintenance_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._maintenance_task
        await EventBus.drain()
        await Database.close()
        await RedisClient.close()
        await super().close()

    async def maintenance(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                if not self.is_ready():
                    Path("/tmp/heimdall-health.json").unlink(missing_ok=True)
                    await asyncio.sleep(5)
                    continue
                await Database.db.command("ping")
                await RedisClient.redis_conn.ping()
                await ModerationService.reconcile(self)
                Path("/tmp/heimdall-health.json").write_text(
                    json.dumps({"at": time(), **snapshot()})
                )
                log.info(
                    "Operational snapshot",
                    extra={"action": "health", "outcome": "ready", "metrics": snapshot()},
                )
            except Exception:
                log.exception("Maintenance failed")
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
