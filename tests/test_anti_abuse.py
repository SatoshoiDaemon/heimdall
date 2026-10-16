import pytest

from src.dtos.payloads import SpamEventDTO
from src.services.anti_abuse_service import AntiAbuseService


@pytest.mark.asyncio
async def test_spam_score_is_accumulated_in_sliding_window():
    hits = [
        await AntiAbuseService.track_spam(SpamEventDTO(1, 2, i, 4, "message", weight=2), 5, 60)
        for i in range(4)
    ]
    assert hits == [False, False, True, False]
