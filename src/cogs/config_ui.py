import discord
from discord import app_commands
from discord.ext import commands

from src.cogs.moderation import PaginationView
from src.core.database import Database
from src.core.event_bus import EventBus
from src.dtos.payloads import LogEventDTO
from src.middlewares.rbac_check import check_permission, has_permissions
from src.services.config_service import ACCESS_PERMISSIONS, ConfigService
from src.services.lock_service import LockService
from src.services.rbac_service import RBACService
from src.utils.embeds import format_error

CATEGORIES = {
    "automod": "AutoMod",
    "verification": "Verification",
    "audit": "Audit",
    "roles": "Exemptions",
    "permissions": "Permissions",
}
RULE_NAMES = {"spam", "mentions", "invites", "urls", "words", "repeated"}
COMMANDS = {
    "warn",
    "unwarn",
    "warnings",
    "ban",
    "unban",
    "kick",
    "timeout",
    "untimeout",
    "mute",
    "unmute",
    "purge",
    "note",
    "notes",
    "history",
    "case",
    "config",
    "*",
}


async def audit_change(interaction, description):
    await EventBus.publish(
        "audit_log",
        LogEventDTO(
            interaction.guild_id,
            "Configuration changed",
            description,
            0x3498DB,
            moderator_id=interaction.user.id,
        ),
    )


class SettingsModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="AutoMod rule")
        self.panel = view
        self.rule = discord.ui.TextInput(
            label="Rule name",
            placeholder="spam, mentions, invites, urls, words, repeated",
            max_length=10,
        )
        self.action = discord.ui.TextInput(
            label="Action: warn/delete/timeout (empty disables)", required=False, max_length=7
        )
        self.threshold = discord.ui.TextInput(label="Threshold (1–1000)", default="3", max_length=4)
        self.duration = discord.ui.TextInput(
            label="Timeout seconds (1–2419200)", default="300", max_length=7
        )
        self.cooldown = discord.ui.TextInput(
            label="Cooldown seconds (1–86400)", default="60", max_length=5
        )
        for field in (self.rule, self.action, self.threshold, self.duration, self.cooldown):
            self.add_item(field)

    async def on_submit(self, interaction):
        if not await self.panel.interaction_check(interaction):
            return
        try:
            name, action = self.rule.value.strip(), self.action.value.strip()
            if name not in RULE_NAMES:
                raise ValueError("Unknown rule.")
            settings = await ConfigService.get_guild_config(interaction.guild_id)
            rules = {k: v.model_dump() for k, v in settings.automod_rules.items()}
            rules[name] = {
                "enabled": bool(action),
                "action": action or "warn",
                "threshold": int(self.threshold.value),
                "duration_seconds": int(self.duration.value),
                "cooldown_seconds": int(self.cooldown.value),
            }
            await ConfigService.update_guild_config(interaction.guild_id, {"automod_rules": rules})
            await audit_change(interaction, f"Rule {name}: {action or 'disabled'}")
        except ValueError as error:
            await interaction.response.send_message(
                embed=format_error(str(error)[:1000]), ephemeral=True
            )
            return
        await self.panel.refresh(interaction)


class WordsModal(discord.ui.Modal, title="Blocked words"):
    words = discord.ui.TextInput(
        label="One word or phrase per line",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=False,
    )

    def __init__(self, panel):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction):
        if not await self.panel.interaction_check(interaction):
            return
        await ConfigService.update_guild_config(
            interaction.guild_id,
            {"blocked_words": [w.strip() for w in self.words.value.splitlines() if w.strip()]},
        )
        await audit_change(interaction, "Updated blocked words")
        await self.panel.refresh(interaction)


class ConfigView(discord.ui.View):
    def __init__(self, config_obj, owner_id):
        super().__init__(timeout=300)
        self.config = config_obj
        self.owner_id = owner_id
        self.category = "automod"
        self.build()

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id or interaction.guild_id != self.config.guild_id:
            await interaction.response.send_message("Open your own /config panel.", ephemeral=True)
            return False
        try:
            return await check_permission(interaction, "config", "manage_guild")
        except app_commands.CheckFailure:
            await interaction.response.send_message(
                "Your configuration permission was revoked.", ephemeral=True
            )
            return False

    def embed(self):
        config = self.config
        embed = discord.Embed(
            title=f"Guild Configuration — {CATEGORIES[self.category]}", color=0x2B2D31
        )
        if self.category == "automod":
            from src.services.anti_abuse_service import AntiAbuseService

            embed.description = "\n".join(
                f"**{name}**: {'on' if rule.enabled else 'off'} · {rule.action} · threshold {rule.threshold} · cooldown {rule.cooldown_seconds}s"
                for name, rule in AntiAbuseService.rules(config).items()
            )
            embed.add_field(name="Word filters", value=f"{len(config.blocked_words)} configured")
        elif self.category == "verification":
            embed.description = (
                f"Verified role: <@&{config.verified_role_id}>"
                if config.verified_role_id
                else "Choose the role assigned after CAPTCHA."
            )
        elif self.category == "audit":
            embed.description = (
                f"Log channel: <#{config.log_channel_id}>"
                if config.log_channel_id
                else "Choose an audit channel."
            )
        elif self.category == "roles":
            embed.description = f"Exempt roles: {len(config.exempt_role_ids)}\nExempt channels: {len(config.exempt_channel_ids)}"
        else:
            embed.description = "Use `/rbac` to list, grant, revoke or inspect effective permissions. Only Discord administrators and the owner may edit RBAC. RBAC grants never bypass role hierarchy."
        return embed

    def build(self):
        self.clear_items()
        select = discord.ui.Select(
            placeholder="Category",
            options=[
                discord.SelectOption(label=v, value=k, default=k == self.category)
                for k, v in CATEGORIES.items()
            ],
        )

        async def category(interaction):
            self.category = select.values[0]
            await self.refresh(interaction)

        select.callback = category
        self.add_item(select)
        if self.category == "automod":
            for label, modal in (("Configure rule", SettingsModal), ("Blocked words", WordsModal)):
                button = discord.ui.Button(label=label)

                async def open_modal(interaction, modal=modal):
                    await interaction.response.send_modal(modal(self))

                button.callback = open_modal
                self.add_item(button)
        if self.category in {"verification", "roles"}:
            roles = discord.ui.RoleSelect(
                placeholder="Verified role" if self.category == "verification" else "Exempt roles",
                min_values=0,
                max_values=1 if self.category == "verification" else 25,
            )

            async def update_roles(interaction):
                chosen = roles.values
                if self.category == "verification":
                    if chosen:
                        role = chosen[0]
                        # A config delegate cannot turn CAPTCHA into role escalation.
                        safe = ACCESS_PERMISSIONS
                        if (
                            role.managed
                            or role.is_default()
                            or role >= interaction.guild.me.top_role
                            or role.permissions.value & ~safe
                        ):
                            await interaction.response.send_message(
                                "Choose a regular access role without elevated permissions, below Heimdall.",
                                ephemeral=True,
                            )
                            return
                    updates = {"verified_role_id": chosen[0].id if chosen else None}
                else:
                    updates = {"exempt_role_ids": [r.id for r in chosen]}
                await ConfigService.update_guild_config(interaction.guild_id, updates)
                await audit_change(interaction, "Updated role settings")
                await self.refresh(interaction)

            roles.callback = update_roles
            self.add_item(roles)
        if self.category in {"audit", "roles"}:
            channels = discord.ui.ChannelSelect(
                placeholder="Audit channel" if self.category == "audit" else "Exempt channels",
                channel_types=[discord.ChannelType.text],
                min_values=0,
                max_values=1 if self.category == "audit" else 25,
            )

            async def update_channels(interaction):
                updates = (
                    {"log_channel_id": channels.values[0].id if channels.values else None}
                    if self.category == "audit"
                    else {"exempt_channel_ids": [c.id for c in channels.values]}
                )
                await ConfigService.update_guild_config(interaction.guild_id, updates)
                await audit_change(interaction, "Updated channel settings")
                await self.refresh(interaction)

            channels.callback = update_channels
            self.add_item(channels)

    async def refresh(self, interaction):
        self.config = await ConfigService.get_guild_config(interaction.guild_id)
        self.build()
        await interaction.response.edit_message(embed=self.embed(), view=self)


class RBACView(PaginationView):
    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id or not (
            interaction.user.id == interaction.guild.owner_id
            or interaction.user.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                "Discord administrator access required.", ephemeral=True
            )
            return False
        return True


class ConfigUI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="config", description="Open the configuration dashboard.")
    @app_commands.guild_only()
    @has_permissions("config", "manage_guild")
    async def config(self, interaction: discord.Interaction):
        settings = await ConfigService.get_guild_config(interaction.guild_id)
        view = ConfigView(settings, interaction.user.id)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    @app_commands.command(
        name="rbac", description="List, grant, revoke or inspect Heimdall permissions."
    )
    @app_commands.guild_only()
    @app_commands.choices(
        operation=[
            app_commands.Choice(name=x, value=x) for x in ("list", "grant", "revoke", "effective")
        ]
    )
    async def rbac(
        self,
        interaction: discord.Interaction,
        operation: str,
        member: discord.Member | None = None,
        role: discord.Role | None = None,
        permission: str | None = None,
    ):
        if (
            interaction.user.id != interaction.guild.owner_id
            and not interaction.user.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                "Discord Administrator or server owner required.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        if operation in {"list", "effective"}:
            query = {"guild_id": interaction.guild_id}
            if operation == "effective":
                if member is None:
                    await interaction.followup.send(
                        "Choose a member for effective permissions.", ephemeral=True
                    )
                    return
                query["$or"] = [
                    {"user_id": member.id},
                    {"role_id": {"$in": [r.id for r in member.roles]}},
                ]
            docs = await RBACService.repo.find_many(query)
            if operation == "effective":
                grants = {c for d in docs for c in d.get("allowed_commands", [])}
                native = {
                    "ban": "ban_members",
                    "unban": "ban_members",
                    "kick": "kick_members",
                    "purge": "manage_messages",
                    "config": "manage_guild",
                }
                effective = []
                admin = (
                    member.id == interaction.guild.owner_id
                    or member.guild_permissions.administrator
                )
                for command in sorted(COMMANDS - {"*"}):
                    if (
                        admin
                        or "*" in grants
                        or command in grants
                        or getattr(
                            member.guild_permissions, native.get(command, "moderate_members"), False
                        )
                    ):
                        effective.append(command)
                lines = [
                    f"**{member}**\nAllowed commands: {', '.join(effective) or 'none'}\n"
                    f"RBAC grants: {', '.join(sorted(grants)) or 'none'}\nRole hierarchy still applies."
                ]
            else:
                lines = [
                    f"**{d['type']} {d.get('user_id') or d.get('role_id')}**\n"
                    + (", ".join(d.get("allowed_commands", [])) or "No grants")
                    for d in docs
                ]
            view = RBACView("Heimdall permissions", lines)
            view.owner_id = interaction.user.id
            await interaction.followup.send(embed=view.embed(), view=view, ephemeral=True)
            return
        if bool(member) == bool(role) or permission not in COMMANDS:
            await interaction.followup.send(
                "Choose exactly one member or role and a valid permission.", ephemeral=True
            )
            return
        if interaction.user.id != interaction.guild.owner_id:
            target = member.top_role if member else role
            if target >= interaction.user.top_role or (
                member and member.id == interaction.guild.owner_id
            ):
                await interaction.followup.send(
                    "Your highest role must be above the recipient.", ephemeral=True
                )
                return
        getter = (
            RBACService.repo.get_user_permissions
            if member
            else RBACService.repo.get_role_permissions
        )
        setter = RBACService.set_user_permission if member else RBACService.set_role_permission
        target_id = member.id if member else role.id
        async with LockService.get_lock(
            f"lock:rbac:{interaction.guild_id}:{'u' if member else 'r'}:{target_id}"
        ):
            current = set(await getter(interaction.guild_id, target_id))
            if operation == "grant":
                current.add(permission)
            elif operation == "revoke":
                current.discard(permission)
            else:
                await interaction.followup.send("Unknown operation.", ephemeral=True)
                return
            async with Database.transaction():
                await setter(interaction.guild_id, target_id, sorted(current))
                await audit_change(interaction, f"RBAC {operation}: {permission} for {target_id}")
        await interaction.followup.send("Permissions updated.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ConfigUI(bot))
