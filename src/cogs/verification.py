import discord
from discord.ext import commands
from discord import app_commands
from src.services.captcha_service import CaptchaService
from src.utils.embeds import format_error, format_success

class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="manual_verify", description="Start verification process.")
    @app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id, i.user.id))
    async def manual_verify(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Create captcha session
        _, buffer = await CaptchaService.create_session(interaction.guild_id, interaction.user.id)
        
        file = discord.File(buffer, filename="captcha.png")
        embed = discord.Embed(title="Verification Required", description="Please use `/solve_captcha <code>` to verify yourself.", color=discord.Color.blurple())
        embed.set_image(url="attachment://captcha.png")
        
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)

    @app_commands.command(name="solve_captcha", description="Solve the image captcha.")
    async def solve_captcha(self, interaction: discord.Interaction, code: str):
        await interaction.response.defer(ephemeral=True)
        
        valid = await CaptchaService.validate(interaction.guild_id, interaction.user.id, code)
        if valid:
            # Here we would normally assign a verified role.
            # Using generic message for demonstration.
            await interaction.followup.send(embed=format_success("Verified", "You have successfully verified your account!"), ephemeral=True)
        else:
            await interaction.followup.send(embed=format_error("Invalid or expired Captcha code. Please start over."), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Verification(bot))
