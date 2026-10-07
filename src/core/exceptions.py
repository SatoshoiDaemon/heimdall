class ModBotException(Exception):
    """Base exception for all Bot errors"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class RBACAccessDenied(ModBotException):
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
