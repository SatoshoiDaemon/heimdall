"""Compare the previous per-message Redis pipeline with the atomic detector.

Use a dedicated disposable Redis DB: TEST_REDIS_URI (default /15).
Prints real measurements as JSON; never asserts timing thresholds in CI.
"""

import asyncio
import json
import os
import statistics
import time
import uuid

from redis.asyncio import Redis

from src.core.redis_client import RedisClient
from src.dtos.payloads import SpamEventDTO
from src.services.anti_abuse_service import AntiAbuseService


async def main():
    conn = Redis.from_url(
        os.environ.get("TEST_REDIS_URI", "redis://localhost:6379/15"), decode_responses=True
    )
    RedisClient.redis_conn = conn
    prefix = "benchmark:" + uuid.uuid4().hex
    results = {}
    samples = 500
    for name in ("previous", "atomic"):
        durations = []
        for i in range(samples):
            started = time.perf_counter()
            if name == "previous":
                now = time.time()
                await conn.zremrangebyscore(prefix, 0, now - 60)
                await conn.zadd(prefix, {f"{i}:1": now})
                await conn.expire(prefix, 60)
                entries = await conn.zrange(prefix, 0, -1)
                sum(int(e.rsplit(":", 1)[1]) for e in entries)
            else:
                await AntiAbuseService.track_spam(
                    SpamEventDTO(0, 0, i, 0, "test"), 20, 60, rule=prefix
                )
            durations.append((time.perf_counter() - started) * 1000)
        results[name] = {
            "samples": samples,
            "median_ms": statistics.median(durations),
            "p95_ms": sorted(durations)[int(samples * 0.95)],
            "redis_round_trips_per_message": 4 if name == "previous" else 1,
        }
    await conn.delete(prefix, f"spam:{{0:0}}:{prefix}", f"spam:{{0:0}}:{prefix}:cooldown")
    await conn.aclose()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
