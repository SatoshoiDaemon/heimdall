import pytest
from fakeredis.aioredis import FakeRedis

from src.core.redis_client import RedisClient
from src.dtos.payloads import SpamEventDTO
from src.services.anti_abuse_service import AntiAbuseService


@pytest.mark.asyncio
async def test_spam_score_is_accumulated_in_sliding_window(monkeypatch):
    redis = FakeRedis(decode_responses=True)
    monkeypatch.setattr(RedisClient, "redis_conn", redis)
    dto = SpamEventDTO(1, 2, 3, 4, "message", weight=2)

    assert await AntiAbuseService.track_spam(dto, threshold=5, window_sec=60) is False
    assert await AntiAbuseService.track_spam(dto, threshold=5, window_sec=60) is False
    assert await AntiAbuseService.track_spam(dto, threshold=5, window_sec=60) is True

    assert await AntiAbuseService.track_spam(dto, threshold=5, window_sec=60) is False
    await redis.aclose()
