import asyncio
import inspect
import logging
from collections.abc import Callable

from src.core.metrics import counters

log = logging.getLogger("modbot.eventbus")


class EventBus:
    _listeners: dict[str, list[Callable]] = {}
    _tasks: set[asyncio.Task] = set()

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
    async def drain(cls):
        if cls._tasks:
            await asyncio.gather(*list(cls._tasks), return_exceptions=True)

    @classmethod
    async def _execute_callback(cls, callback, *args, **kwargs):
        try:
            result = callback(*args, **kwargs)
            if inspect.isawaitable(result):
                await result
        except Exception:
            counters["event_callback_failed"] += 1
            log.exception("Event callback failed: %s", getattr(callback, "__name__", str(callback)))
