import discord
from discord.ext import commands
from discord import app_commands
from src.middlewares.rbac_check import has_permissions
from src.services.config_service import ConfigService

class ConfigUI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="config", description="Open the configuration dashboard.")
    @has_permissions("config")
    async def config(self, interaction: discord.Interaction):
        config = await ConfigService.get_guild_config(interaction.guild_id)
        
        embed = discord.Embed(title="⚙️ Guild Configuration", color=0x2b2d31)
        embed.add_field(name="Anti-Spam", value="✅ Enabled" if config.anti_spam_enabled else "❌ Disabled")
        embed.add_field(name="Anti-Link", value="✅ Enabled" if config.anti_link_enabled else "❌ Disabled")
        embed.add_field(name="Anti-Mention", value="✅ Enabled" if config.anti_mention_enabled else "❌ Disabled")
        
        view = ConfigView(config)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ConfigView(discord.ui.View):
    def __init__(self, config_obj):
        super().__init__(timeout=300)
        self.config = config_obj

    @discord.ui.button(label="Toggle Anti-Spam", style=discord.ButtonStyle.primary)
    async def toggle_spam(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_val = not self.config.anti_spam_enabled
        await ConfigService.update_guild_config(interaction.guild_id, {"anti_spam_enabled": new_val})
        self.config.anti_spam_enabled = new_val
        await interaction.followup.send(f"Anti-Spam is now {'enabled' if new_val else 'disabled'}.", ephemeral=True)

    @discord.ui.button(label="Toggle Anti-Link", style=discord.ButtonStyle.secondary)
    async def toggle_link(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_val = not self.config.anti_link_enabled
        await ConfigService.update_guild_config(interaction.guild_id, {"anti_link_enabled": new_val})
        self.config.anti_link_enabled = new_val
        await interaction.followup.send(f"Anti-Link is now {'enabled' if new_val else 'disabled'}.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ConfigUI(bot))
