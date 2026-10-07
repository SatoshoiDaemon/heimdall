import discord
from discord import app_commands
from src.services.rbac_service import RBACService
from src.core.exceptions import PermissionDenied, RBACAccessDenied

async def check_permission(
    interaction: discord.Interaction, command_name: str, native_permission: str | None = None
) -> bool:
    guild = interaction.guild
    if not guild:
        return False

    user = interaction.user
    roles = [r.id for r in user.roles]

    if user.id == guild.owner_id or user.guild_permissions.administrator:
        return True

    native_allowed = bool(
        native_permission and getattr(user.guild_permissions, native_permission, False)
    )
    rbac_allowed = await RBACService.has_permission(guild.id, user.id, roles, command_name)
    if not native_allowed and not rbac_allowed:
        raise RBACAccessDenied(f"You do not have permission to execute `{command_name}`.")
    return True


def has_permissions(command_name: str, native_permission: str | None = None):
    async def predicate(interaction: discord.Interaction) -> bool:
        return await check_permission(interaction, command_name, native_permission)

    return app_commands.check(predicate)


def has_moderation_permission(command_name: str, native_permission: str):
    """Allow Discord's native permission OR an explicit Heimdall RBAC grant."""
    return has_permissions(command_name, native_permission)
