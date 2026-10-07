import asyncio
import pytest
from src.core.event_bus import EventBus


@pytest.mark.asyncio
async def test_event_bus_dispatches_sync_and_async_callbacks():
    received = []

    def sync_callback(value):
        received.append(("sync", value))

    async def async_callback(value):
        received.append(("async", value))

    EventBus.subscribe("event", sync_callback)
    EventBus.subscribe("event", async_callback)
    EventBus.emit("event", 42)
    await asyncio.sleep(0)

    assert sorted(received) == [("async", 42), ("sync", 42)]


@pytest.mark.asyncio
async def test_event_bus_contains_callback_failures():
    received = []

    def failing_callback():
        raise RuntimeError("expected failure")

    def healthy_callback():
        received.append(True)

    EventBus.subscribe("event", failing_callback)
    EventBus.subscribe("event", healthy_callback)
    EventBus.emit("event")
    await asyncio.sleep(0)

    assert received == [True]
