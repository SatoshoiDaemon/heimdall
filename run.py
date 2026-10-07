import asyncio
from src.core.logger import setup_logger
from src.core.config import config
from src.core.bot import ModBot
import sys

def main():
    logger = setup_logger()
    logger.info("Starting up Bot1 ModBot...")

    if not config.BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set in the environment variables.")
        sys.exit(1)

    bot = ModBot()

    try:
        # We start the bot using discord.py's native interface
        bot.run(config.BOT_TOKEN, log_handler=None) # We already setup our custom logger
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down.")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        
if __name__ == "__main__":
    main()
