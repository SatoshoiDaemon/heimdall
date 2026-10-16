"""PaaS entrypoint: a Python process, environment variables and MongoDB."""

import asyncio
import signal
import sys
from contextlib import suppress

from src.core.config import config
from src.core.exceptions import ConfigurationError
from src.core.logger import setup_logger


async def serve(token):
    from src.core.bot import ModBot

    bot = ModBot()
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    installed = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
            installed.append(sig)
        except (NotImplementedError, RuntimeError):
            # Platforms without loop signal handlers retain KeyboardInterrupt.
            pass
    start_task = None
    stop_task = None
    try:
        async with bot:
            start_task = asyncio.create_task(bot.start(token, reconnect=True))
            stop_task = asyncio.create_task(stop.wait())
            done, _ = await asyncio.wait(
                (start_task, stop_task), return_when=asyncio.FIRST_COMPLETED
            )
            if start_task in done:
                await start_task  # Propagate startup/gateway failure to exit code.
            else:
                await bot.close()
            if bot.failure is not None:
                raise bot.failure
    finally:
        for task in (start_task, stop_task):
            if task is not None and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        await bot.close()
        for sig in installed:
            loop.remove_signal_handler(sig)


def main():
    logger = setup_logger()
    try:
        config.validate()
    except ConfigurationError as error:
        logger.critical("Invalid configuration: %s", error)
        return 1
    try:
        logger.info("Starting Heimdall...")
        asyncio.run(serve(config.BOT_TOKEN))
    except KeyboardInterrupt:
        logger.info("Interrupted; shutdown complete.")
    except Exception:
        logger.exception("Fatal error while running Heimdall.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
