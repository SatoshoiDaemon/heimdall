import time
from src.core.redis_client import RedisClient
from src.core.event_bus import EventBus
from src.dtos.payloads import SpamEventDTO

class AntiAbuseService:
    @staticmethod
    async def track_spam(dto: SpamEventDTO, threshold: int, window_sec: int) -> bool:
        """
        Sliding Window Rate Limiter using Redis Sorted Sets.
        Returns True if threshold is exceeded.
        """
        conn = RedisClient.redis_conn
        key = f"spam:{dto.guild_id}:{dto.user_id}"
        now = time.time()
        
        # Remove old entries outside the window
        await conn.zremrangebyscore(key, 0, now - window_sec)
        
        # Add new event (score = timestamp, member = timestamp-weight)
        # Using a slight random suffix on member to prevent collisions if exact same timestamp
        val = f"{now}-{dto.weight}"
        await conn.zadd(key, {val: now})
        
        # Set expiration to cleanup old keys automatically
        await conn.expire(key, window_sec)
        
        # Calculate score within window
        # Get all entries and sum weights
        entries = await conn.zrange(key, 0, -1)
        total_score = sum(int(e.split('-')[1]) for e in entries)
        
        if total_score >= threshold:
            # Emit spam detected event to decouple punishment logic
            EventBus.emit("spam_detected", dto)
            return True
            
        return False
