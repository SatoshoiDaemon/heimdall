from discord import app_commands


class ModBotException(Exception):
    """Base exception for all Bot errors"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class ConfigurationError(ModBotException):
    """Raised when the bot cannot start with the configured environment."""

    pass


class ModerationError(ModBotException):
    """Base exception for expected moderation failures."""

    pass


class PermissionDenied(ModerationError):
    pass


class InvalidTarget(ModerationError):
    pass


class InvalidDuration(ModerationError):
    pass


class CaseNotFound(ModerationError):
    pass


class InvalidCase(ModerationError):
    pass


class RBACAccessDenied(ModBotException, app_commands.CheckFailure):
    """Raised when a user lacks permission for a command"""

    pass


class RateLimitExceeded(ModBotException):
    """Raised when a user triggers a custom rate limit"""

    pass


class InvalidCaptcha(ModBotException):
    """Raised when captcha validation fails"""

    pass


class ItemNotFound(ModBotException):
    """Raised when repository cannot find item"""

    pass
