import sys

from src.core.config import config
from src.core.exceptions import ConfigurationError
from src.core.logger import setup_logger

def main():
    logger = setup_logger()
    logger.info("Starting up Heimdall...")

    try:
        config.validate()
    except ConfigurationError as error:
        logger.critical("Invalid configuration: %s", error)
        sys.exit(1)

    from src.core.bot import ModBot

    bot = ModBot()

    try:
        # We start the bot using discord.py's native interface
        bot.run(config.BOT_TOKEN, log_handler=None) # We already setup our custom logger
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down.")
    except Exception:
        logger.exception("Fatal error while running Heimdall.")
        
if __name__ == "__main__":
    main()
