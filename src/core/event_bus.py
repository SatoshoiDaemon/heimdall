import asyncio
import inspect
import logging
from collections.abc import Callable

from src.core.metrics import counters

log = logging.getLogger("modbot.eventbus")


class EventBus:
    _listeners: dict[str, list[Callable]] = {}
    _tasks: set[asyncio.Task] = set()
    MAX_TASKS = 256

    @classmethod
    def subscribe(cls, event_name, callback):
        listeners = cls._listeners.setdefault(event_name, [])
        if callback not in listeners:
            listeners.append(callback)

    @classmethod
    def unsubscribe(cls, event_name, callback):
        if callback in cls._listeners.get(event_name, []):
            cls._listeners[event_name].remove(callback)

    @classmethod
    def emit(cls, event_name, *args, **kwargs):
        for callback in cls._listeners.get(event_name, []):
            if len(cls._tasks) >= cls.MAX_TASKS:
                counters["event_backpressure"] += 1
                log.error("Event task limit reached; use awaited publish for critical events")
                return False
            task = asyncio.create_task(cls._execute_callback(callback, *args, **kwargs))
            cls._tasks.add(task)
            task.add_done_callback(cls._tasks.discard)

    @classmethod
    async def publish(cls, event_name, *args, **kwargs):
        """Await critical consumers and propagate failures to the caller."""
        for callback in cls._listeners.get(event_name, []):
            result = callback(*args, **kwargs)
            if inspect.isawaitable(result):
                await result

    @classmethod
    async def drain(cls, timeout=10):
        tasks = list(cls._tasks)
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout)
            except TimeoutError:
                log.warning("Event shutdown timeout; unfinished callbacks cancelled")
            finally:
                cls._tasks.difference_update(tasks)

    @classmethod
    async def _execute_callback(cls, callback, *args, **kwargs):
        try:
            result = callback(*args, **kwargs)
            if inspect.isawaitable(result):
                await result
        except Exception:
            counters["event_callback_failed"] += 1
            log.exception("Event callback failed: %s", getattr(callback, "__name__", str(callback)))
