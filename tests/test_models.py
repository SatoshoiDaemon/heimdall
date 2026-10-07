from datetime import datetime, timezone

from src.models.domain import GuildConfig, RolePermission, Warn


def test_mongo_object_id_values_are_normalized():
    warn = Warn(
        _id=object(),
        guild_id=1,
        user_id=2,
        moderator_id=3,
        reason="test",
        created_at=datetime.now(timezone.utc),
    )

    assert isinstance(warn.id, str)


def test_permission_lists_have_independent_defaults():
    first = RolePermission(_id="first", guild_id=1, role_id=2)
    second = RolePermission(_id="second", guild_id=1, role_id=3)
    first.allowed_commands.append("warn")

    assert second.allowed_commands == []


def test_guild_config_uses_domain_defaults():
    config = GuildConfig(_id="config", guild_id=1)

    assert config.anti_spam_enabled is False
    assert config.mention_limit_per_msg == 5
