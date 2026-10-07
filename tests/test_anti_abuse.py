import pytest

from src.core.redis_client import RedisClient
from src.dtos.payloads import SpamEventDTO
from src.services.anti_abuse_service import AntiAbuseService


class FakeRedis:
    def __init__(self):
        self.entries = {}

    async def zremrangebyscore(self, key, _minimum, maximum):
        self.entries[key] = [entry for entry in self.entries.get(key, []) if entry[1] > maximum]

    async def zadd(self, key, values):
        self.entries.setdefault(key, []).extend((member, score) for member, score in values.items())

    async def expire(self, _key, _seconds):
        return True

    async def zrange(self, key, _start, _stop):
        return [member for member, _score in self.entries.get(key, [])]


@pytest.mark.asyncio
async def test_spam_score_is_accumulated_in_sliding_window(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(RedisClient, "redis_conn", redis)
    dto = SpamEventDTO(1, 2, 3, 4, "message", weight=2)

    assert await AntiAbuseService.track_spam(dto, threshold=5, window_sec=60) is False
    assert await AntiAbuseService.track_spam(dto, threshold=5, window_sec=60) is False
    assert await AntiAbuseService.track_spam(dto, threshold=5, window_sec=60) is True
