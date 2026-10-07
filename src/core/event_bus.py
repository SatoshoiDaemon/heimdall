import asyncio
import inspect
from typing import Callable, Dict, List, Any
import logging

log = logging.getLogger("modbot.eventbus")

class EventBus:
    _listeners: Dict[str, List[Callable]] = {}

    @classmethod
    def subscribe(cls, event_name: str, callback: Callable):
        if event_name not in cls._listeners:
            cls._listeners[event_name] = []
        cls._listeners[event_name].append(callback)

    @classmethod
    def emit(cls, event_name: str, *args, **kwargs):
        if event_name in cls._listeners:
            for callback in cls._listeners[event_name]:
                # Fire and forget
                asyncio.create_task(cls._execute_callback(callback, *args, **kwargs))

    @classmethod
    async def _execute_callback(cls, callback: Callable, *args, **kwargs):
        try:
            if inspect.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            log.error(f"Error in EventBus callback for {callback.__name__}: {e}")
