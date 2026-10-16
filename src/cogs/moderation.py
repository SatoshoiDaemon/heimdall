from collections.abc import Awaitable
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from src.core.exceptions import ModBotException, ModerationError
from src.dtos.payloads import NoteRequestDTO, WarnRequestDTO
from src.middlewares.rbac_check import has_moderation_permission
from src.models.domain import Case
from src.services.moderation_service import ModerationService
from src.utils.embeds import format_error, format_success


class PaginationView(discord.ui.View):
    def __init__(self, title: str, lines: list[str], page_size: int = 5, page: int = 1):
        super().__init__(timeout=180)
        self.title = title
        self.lines = lines
        self.page_size = page_size
        if page_size < 1:
            raise ModerationError("Page size must be positive.")
        if not 1 <= page <= self.page_count:
            raise ModerationError(f"Page must be between 1 and {self.page_count}.")
        self.page = page - 1
        self.owner_id = None
        self.permission = None
        self.message: discord.InteractionMessage | None = None
        self._refresh_buttons()

    async def interaction_check(self, interaction):
        if self.owner_id is not None and interaction.user.id != self.owner_id:
            await interaction.response.send_message("Open your own query.", ephemeral=True)
            return False
        if self.permission:
            from src.middlewares.rbac_check import check_permission

            return await check_permission(interaction, self.permission, "moderate_members")
        return True

    @property
    def page_count(self) -> int:
        return max(1, (len(self.lines) + self.page_size - 1) // self.page_size)

    def embed(self) -> discord.Embed:
        start = self.page * self.page_size
        content = "\n\n".join(self.lines[start : start + self.page_size]) or "No records found."
        return discord.Embed(
            title=self.title,
            description=content,
            color=discord.Color.blurple(),
        ).set_footer(text=f"Page {self.page + 1}/{self.page_count}")

    def _refresh_buttons(self):
        self.previous.disabled = self.page <= 0
        self.next.disabled = self.page >= self.page_count - 1

    async def _update(self, interaction: discord.Interaction, delta: int):
        self.page = max(0, min(self.page_count - 1, self.page + delta))
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._update(interaction, -1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._update(interaction, 1)


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _guild(interaction: discord.Interaction) -> discord.Guild:
        if interaction.guild is None:
            raise ModerationError("This command can only be used inside a server.")
        return interaction.guild

    @staticmethod
    def _case_text(case: Case) -> str:
        duration = f"\n**Duration:** {case.duration_seconds}s" if case.duration_seconds else ""
        related = f"\n**Related:** #{case.related_case_number}" if case.related_case_number else ""
        state = "revoked" if case.revoked else case.status
        target = f"<@{case.target_user_id}>" if case.target_user_id else "Current channel"
        return (
            f"**Case #{case.case_number} — {case.action}** ({state})\n"
            f"**Target:** {target}\n"
            f"**Moderator:** <@{case.moderator_id}> | {case.origin}\n"
            f"**Reason:** {case.reason}{duration}{related}"
        )

    async def _execute(self, interaction: discord.Interaction, operation: Awaitable, title: str):
        await interaction.response.defer(ephemeral=True)
        try:
            result = await operation
        except ModBotException as error:
            await interaction.followup.send(embed=format_error(str(error)), ephemeral=True)
        except discord.HTTPException:
            await interaction.followup.send(
                embed=format_error(
                    "Discord rejected the request. Check permissions and try again."
                ),
                ephemeral=True,
            )
        else:
            if isinstance(result, Case):
                description = self._case_text(result)
            else:
                description = str(result)
            await interaction.followup.send(
                embed=format_success(title, description), ephemeral=True
            )

    async def _send_cases(self, interaction: discord.Interaction, title: str, cases: list[Case]):
        lines = [self._case_text(case) for case in cases]
        view = PaginationView(title, lines)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    @app_commands.command(name="warn", description="Warn a member.")
    @app_commands.describe(target="Member to warn", reason="Reason for the warning")
    @has_moderation_permission("warn", "moderate_members")
    async def warn(self, interaction: discord.Interaction, target: discord.Member, reason: str):
        guild = self._guild(interaction)
        await self._execute(
            interaction,
            ModerationService.issue_warn(
                WarnRequestDTO(guild.id, target.id, interaction.user.id, reason), guild=guild
            ),
            "Warning created",
        )

    @app_commands.command(name="unwarn", description="Revoke a warning case.")
    @app_commands.describe(case_number="Warning case number", reason="Reason for revocation")
    @has_moderation_permission("unwarn", "moderate_members")
    async def unwarn(self, interaction: discord.Interaction, case_number: int, reason: str):
        guild = self._guild(interaction)
        await self._execute(
            interaction,
            ModerationService.unwarn(
                guild.id, interaction.user.id, case_number, reason, guild=guild
            ),
            "Warning revoked",
        )

    @app_commands.command(name="warnings", description="List warnings for a member.")
    @app_commands.describe(target="Member whose warnings should be listed", page="Page number")
    @has_moderation_permission("warnings", "moderate_members")
    async def warnings(
        self, interaction: discord.Interaction, target: discord.Member, page: int = 1
    ):
        guild = self._guild(interaction)
        await interaction.response.defer(ephemeral=True)
        try:
            warnings = await ModerationService.warnings(guild.id, target.id)
            lines = [
                f"**Warning #{getattr(warning, 'case_number', 'legacy')}**\n"
                f"**Reason:** {warning.reason}\n"
                f"**Moderator:** <@{warning.moderator_id}>\n"
                f"**Revoked:** {'yes' if warning.revoked else 'no'}"
                for warning in warnings
            ]
            view = PaginationView(f"Warnings — {target}", lines, page=page)
            view.owner_id, view.permission = interaction.user.id, "warnings"
            await interaction.followup.send(embed=view.embed(), view=view, ephemeral=True)
        except ModBotException as error:
            await interaction.followup.send(embed=format_error(str(error)), ephemeral=True)

    @app_commands.command(name="ban", description="Ban a member.")
    @app_commands.describe(
        target="Member to ban",
        reason="Reason for the ban",
        delete_message_seconds="Messages to delete",
    )
    @has_moderation_permission("ban", "ban_members")
    async def ban(
        self,
        interaction: discord.Interaction,
        target: discord.Member,
        reason: str,
        delete_message_seconds: int = 0,
    ):
        guild = self._guild(interaction)
        await self._execute(
            interaction,
            ModerationService.ban(
                guild, target, interaction.user.id, reason, delete_message_seconds
            ),
            "Member banned",
        )

    @app_commands.command(name="unban", description="Remove a member ban.")
    @app_commands.describe(user_id="Banned user's ID", reason="Reason for the unban")
    @has_moderation_permission("unban", "ban_members")
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str):
        guild = self._guild(interaction)
        try:
            parsed_user_id = int(user_id)
        except ValueError:
            await interaction.response.send_message(
                embed=format_error("User ID must be numeric."), ephemeral=True
            )
            return
        await self._execute(
            interaction,
            ModerationService.unban(guild, parsed_user_id, interaction.user.id, reason),
            "Member unbanned",
        )

    @app_commands.command(name="kick", description="Kick a member.")
    @app_commands.describe(target="Member to kick", reason="Reason for the kick")
    @has_moderation_permission("kick", "kick_members")
    async def kick(self, interaction: discord.Interaction, target: discord.Member, reason: str):
        guild = self._guild(interaction)
        await self._execute(
            interaction,
            ModerationService.kick(guild, target, interaction.user.id, reason),
            "Member kicked",
        )

    @app_commands.command(name="timeout", description="Timeout a member.")
    @app_commands.describe(
        target="Member to timeout", duration="Duration such as 30m, 1h or 7d", reason="Reason"
    )
    @has_moderation_permission("timeout", "moderate_members")
    async def timeout(
        self, interaction: discord.Interaction, target: discord.Member, duration: str, reason: str
    ):
        guild = self._guild(interaction)
        await self._execute(
            interaction,
            ModerationService.timeout(
                guild,
                target,
                interaction.user.id,
                ModerationService.parse_duration(duration),
                reason,
            ),
            "Member timed out",
        )

    @app_commands.command(name="untimeout", description="Remove a member timeout.")
    @app_commands.describe(
        target="Member to untimeout", case_number="Timeout case number", reason="Reason"
    )
    @has_moderation_permission("untimeout", "moderate_members")
    async def untimeout(
        self,
        interaction: discord.Interaction,
        target: discord.Member,
        case_number: int,
        reason: str,
    ):
        guild = self._guild(interaction)
        await self._execute(
            interaction,
            ModerationService.untimeout(guild, target, interaction.user.id, case_number, reason),
            "Timeout removed",
        )

    @app_commands.command(name="mute", description="Mute a member using Discord timeout.")
    @app_commands.describe(
        target="Member to mute", duration="Duration such as 30m, 1h or 7d", reason="Reason"
    )
    @has_moderation_permission("mute", "moderate_members")
    async def mute(
        self, interaction: discord.Interaction, target: discord.Member, duration: str, reason: str
    ):
        guild = self._guild(interaction)
        await self._execute(
            interaction,
            ModerationService.mute(
                guild,
                target,
                interaction.user.id,
                ModerationService.parse_duration(duration),
                reason,
            ),
            "Member muted",
        )

    @app_commands.command(name="unmute", description="Remove a timeout created through mute.")
    @app_commands.describe(
        target="Member to unmute", case_number="Timeout case number", reason="Reason"
    )
    @has_moderation_permission("unmute", "moderate_members")
    async def unmute(
        self,
        interaction: discord.Interaction,
        target: discord.Member,
        case_number: int,
        reason: str,
    ):
        guild = self._guild(interaction)
        await self._execute(
            interaction,
            ModerationService.unmute(guild, target, interaction.user.id, case_number, reason),
            "Mute removed",
        )

    @app_commands.command(
        name="purge", description="Delete recent messages from the current channel."
    )
    @app_commands.describe(amount="Number of messages from 1 to 100", reason="Reason")
    @has_moderation_permission("purge", "manage_messages")
    async def purge(self, interaction: discord.Interaction, amount: int, reason: str):
        self._guild(interaction)
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=format_error("This command requires a text channel."), ephemeral=True
            )
            return
        await self._execute(
            interaction,
            ModerationService.purge(interaction.channel, interaction.user.id, amount, reason),
            "Messages purged",
        )

    @app_commands.command(name="note", description="Add a private moderation note.")
    @app_commands.describe(target="Member associated with the note", note_text="Private note text")
    @has_moderation_permission("note", "moderate_members")
    async def note(self, interaction: discord.Interaction, target: discord.Member, note_text: str):
        guild = self._guild(interaction)
        await self._execute(
            interaction,
            ModerationService.add_note(
                NoteRequestDTO(guild.id, target.id, interaction.user.id, note_text), guild=guild
            ),
            "Note created",
        )

    @app_commands.command(name="notes", description="List private notes for a member.")
    @app_commands.describe(target="Member whose notes should be listed", page="Page number")
    @has_moderation_permission("notes", "moderate_members")
    async def notes(self, interaction: discord.Interaction, target: discord.Member, page: int = 1):
        guild = self._guild(interaction)
        await interaction.response.defer(ephemeral=True)
        try:
            notes = await ModerationService.notes(guild.id, target.id)
            lines = [f"**Note** — {note.note}\nModerator: <@{note.moderator_id}>" for note in notes]
            view = PaginationView(f"Notes — {target}", lines, page=page)
            view.owner_id, view.permission = interaction.user.id, "notes"
            await interaction.followup.send(embed=view.embed(), view=view, ephemeral=True)
        except ModBotException as error:
            await interaction.followup.send(embed=format_error(str(error)), ephemeral=True)

    @app_commands.command(name="history", description="View moderation history.")
    @app_commands.describe(target="Optional member", page="Page number")
    @has_moderation_permission("history", "moderate_members")
    async def history(
        self,
        interaction: discord.Interaction,
        target: discord.Member | None = None,
        page: int = 1,
        moderator: discord.Member | None = None,
        action: str | None = None,
        origin: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ):
        guild = self._guild(interaction)
        await interaction.response.defer(ephemeral=True)
        try:
            from src.cogs.case_views import HistoryView

            if page < 1:
                raise ModerationError("Page must be at least 1.")
            try:
                start = datetime.fromisoformat(since).replace(tzinfo=UTC) if since else None
                end = datetime.fromisoformat(until).replace(tzinfo=UTC) if until else None
            except ValueError as error:
                raise ModerationError(
                    "Dates must use ISO format, for example 2026-10-15."
                ) from error
            if start and end and start > end:
                raise ModerationError("Start must be before end.")
            if origin is not None and origin not in {"manual", "automatic"}:
                raise ModerationError("Origin must be manual or automatic.")
            view = HistoryView(
                guild.id,
                interaction.user.id,
                page,
                {
                    "target_user_id": target.id if target else None,
                    "moderator_id": moderator.id if moderator else None,
                    "action": action.upper() if action else None,
                    "origin": origin,
                    "since": start,
                    "until": end,
                },
                self._case_text,
            )
            await view.load()
            await interaction.followup.send(embed=view.embed(), view=view, ephemeral=True)
        except ModBotException as error:
            await interaction.followup.send(embed=format_error(str(error)), ephemeral=True)

    @app_commands.command(name="case", description="View a moderation case.")
    @app_commands.describe(case_number="Case number")
    @has_moderation_permission("case", "moderate_members")
    async def case(self, interaction: discord.Interaction, case_number: int):
        guild = self._guild(interaction)
        await self._execute(
            interaction,
            ModerationService.get_case(guild.id, case_number),
            f"Case #{case_number}",
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
