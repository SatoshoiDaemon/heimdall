import logging
import sys

def setup_logger():
    # Use standard logging but cleanly formatted for standard output
    logger = logging.getLogger("modbot")
    logger.setLevel(logging.INFO)
    
    # Prevent adding handlers multiple times in case of reloads
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Silence discord.py annoying debugs
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)

    return logger
