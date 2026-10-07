import discord
from discord import app_commands
from src.services.rbac_service import RBACService
from src.utils.embeds import format_error
from src.core.exceptions import RBACAccessDenied

def has_permissions(command_name: str):
    async def predicate(interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if not guild:
            return False # Only guild commands
            
        user = interaction.user
        roles = [r.id for r in user.roles]
        
        # Bypass for server owner or admin
        if user.id == guild.owner_id or user.guild_permissions.administrator:
            return True

        has_perm = await RBACService.has_permission(guild.id, user.id, roles, command_name)
        if not has_perm:
            raise RBACAccessDenied(f"You do not have permission to execute `{command_name}`.")
        return True
        
    return app_commands.check(predicate)
