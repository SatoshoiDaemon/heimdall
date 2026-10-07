import pytest

from src.core.event_bus import EventBus


@pytest.fixture(autouse=True)
def reset_event_bus():
    EventBus._listeners.clear()
    yield
    EventBus._listeners.clear()
