import pytest

from src.core.config import Config
from src.core.exceptions import ConfigurationError


def valid_environment(**overrides):
    values = {
        "BOT_TOKEN": "test-token",
        "MONGO_URI": "mongodb://localhost:27017",
        "MONGO_DB_NAME": "heimdall_test",
    }
    values.update(overrides)
    return values


def test_valid_configuration():
    config = Config(valid_environment()).validate()

    assert config.MONGO_DB_NAME == "heimdall_test"
    assert config.CAPTCHA_TIMEOUT_SECONDS == 300


@pytest.mark.parametrize("missing", ["BOT_TOKEN", "MONGO_URI", "MONGO_DB_NAME"])
def test_required_configuration_is_enforced(missing):
    environment = valid_environment()
    environment.pop(missing)

    with pytest.raises(ConfigurationError, match=missing):
        Config(environment).validate()


def test_invalid_uri_is_rejected():
    with pytest.raises(ConfigurationError, match="MONGO_URI"):
        Config(valid_environment(MONGO_URI="http://localhost")).validate()


def test_invalid_timeout_is_rejected():
    with pytest.raises(ConfigurationError, match="CAPTCHA_TIMEOUT_SECONDS"):
        Config(valid_environment(CAPTCHA_TIMEOUT_SECONDS="0")).validate()


def test_optional_guild_id_must_be_positive():
    with pytest.raises(ConfigurationError, match="GUILD_ID"):
        Config(valid_environment(GUILD_ID="not-a-number")).validate()
