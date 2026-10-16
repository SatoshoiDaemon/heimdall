import os
from collections.abc import Mapping
from urllib.parse import urlparse

from dotenv import load_dotenv

from src.core.exceptions import ConfigurationError

load_dotenv()


class Config:
    def __init__(self, environ: Mapping[str, str] | None = None):
        env = os.environ if environ is None else environ
        self.BOT_TOKEN = env.get("BOT_TOKEN")
        self.MONGO_URI = env.get("MONGO_URI")
        self.MONGO_DB_NAME = env.get("MONGO_DB_NAME")
        self.REDIS_URI = env.get("REDIS_URI")
        self._captcha_timeout_raw = env.get("CAPTCHA_TIMEOUT_SECONDS", "300")
        self._log_worker_interval_raw = env.get("LOG_WORKER_INTERVAL_SECONDS", "5")
        self.CAPTCHA_TIMEOUT_SECONDS: int = 300
        self.LOG_WORKER_INTERVAL_SECONDS: int = 5
        self.GUILD_ID = env.get("GUILD_ID")

    @staticmethod
    def _positive_int(raw_value: str, name: str) -> int:
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"{name} must be a positive integer.") from exc
        if value <= 0:
            raise ConfigurationError(f"{name} must be a positive integer.")
        return value

    @staticmethod
    def _validate_uri(value: str | None, name: str, schemes: set[str]) -> None:
        if not value:
            raise ConfigurationError(f"{name} is required.")
        parsed = urlparse(value)
        if parsed.scheme not in schemes or not parsed.netloc:
            allowed = ", ".join(sorted(schemes))
            raise ConfigurationError(f"{name} must be a valid URI using: {allowed}.")

    def validate(self) -> "Config":
        self.CAPTCHA_TIMEOUT_SECONDS = self._positive_int(
            self._captcha_timeout_raw, "CAPTCHA_TIMEOUT_SECONDS"
        )
        self.LOG_WORKER_INTERVAL_SECONDS = self._positive_int(
            self._log_worker_interval_raw, "LOG_WORKER_INTERVAL_SECONDS"
        )
        if not self.BOT_TOKEN or self.BOT_TOKEN == "your_bot_token_here":
            raise ConfigurationError("BOT_TOKEN is required.")
        if not self.MONGO_DB_NAME or not self.MONGO_DB_NAME.strip():
            raise ConfigurationError("MONGO_DB_NAME is required.")

        self._validate_uri(self.MONGO_URI, "MONGO_URI", {"mongodb", "mongodb+srv"})
        self._validate_uri(self.REDIS_URI, "REDIS_URI", {"redis", "rediss"})

        if self.CAPTCHA_TIMEOUT_SECONDS > 86_400:
            raise ConfigurationError("CAPTCHA_TIMEOUT_SECONDS cannot exceed 86400.")
        if self.LOG_WORKER_INTERVAL_SECONDS > 3_600:
            raise ConfigurationError("LOG_WORKER_INTERVAL_SECONDS cannot exceed 3600.")
        if self.GUILD_ID is not None:
            try:
                if int(self.GUILD_ID) <= 0:
                    raise ValueError
            except ValueError as exc:
                raise ConfigurationError("GUILD_ID must be a positive integer when set.") from exc
        return self


config = Config()
