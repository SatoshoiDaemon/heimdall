import discord

def format_success(title: str, description: str) -> discord.Embed:
    return discord.Embed(title=f"✅ {title}", description=description, color=discord.Color.green())

def format_error(description: str) -> discord.Embed:
    return discord.Embed(title="❌ Error", description=description, color=discord.Color.red())

def format_info(title: str, description: str) -> discord.Embed:
    return discord.Embed(title=f"ℹ️ {title}", description=description, color=discord.Color.blue())
