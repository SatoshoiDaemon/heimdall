import discord

from src.middlewares.rbac_check import check_permission
from src.services.moderation_service import ModerationService


class RecordsView(discord.ui.View):
    """Database pages are fetched once per navigation, including all filters."""

    def __init__(
        self, guild_id, owner_id, page, filters, render, kind="history", title="Moderation history"
    ):
        super().__init__(timeout=180)
        self.guild_id, self.owner_id, self.page = guild_id, owner_id, page
        self.filters, self.render = filters, render
        self.kind, self.title = kind, title
        self.rows = []
        self.has_next = False

    async def load(self):
        if self.page < 1:
            from src.core.exceptions import ModerationError

            raise ModerationError("Page must be at least 1.")
        loader = getattr(ModerationService, self.kind)
        rows = await loader(self.guild_id, page=self.page, page_size=5, **self.filters)
        self.rows = rows
        following = await loader(self.guild_id, page=self.page + 1, page_size=5, **self.filters)
        self.has_next = bool(following)
        self.previous.disabled = self.page <= 1
        self.next.disabled = not self.has_next
        if self.page > 1 and not rows:
            from src.core.exceptions import ModerationError

            raise ModerationError("Page does not exist.")

    def embed(self):
        text = "\n\n".join(self.render(row) for row in self.rows) or "No cases found."
        return discord.Embed(title=self.title, description=text[:4096], color=0x5865F2).set_footer(
            text=f"Page {self.page}"
        )

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id or interaction.guild_id != self.guild_id:
            await interaction.response.send_message("Open your own /history.", ephemeral=True)
            return False
        try:
            return await check_permission(interaction, self.kind, "moderate_members")
        except discord.app_commands.CheckFailure:
            await interaction.response.send_message("Your permission was revoked.", ephemeral=True)
            return False

    async def move(self, interaction, delta):
        await interaction.response.defer()
        previous_page = self.page
        self.page = max(1, self.page + delta)
        try:
            await self.load()
        except Exception as error:
            from src.core.exceptions import ModBotException

            self.page = previous_page
            if not isinstance(error, ModBotException):
                raise
            await interaction.followup.send(str(error), ephemeral=True)
            return
        await interaction.edit_original_response(embed=self.embed(), view=self)

    @discord.ui.button(label="Previous")
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.move(interaction, -1)

    @discord.ui.button(label="Next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.move(interaction, 1)


HistoryView = RecordsView
