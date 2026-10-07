import random
import string
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from src.core.redis_client import RedisClient
from src.core.config import config

class CaptchaService:
    @staticmethod
    def generate_image(text: str) -> BytesIO:
        # Simple captcha image generator
        img = Image.new('RGB', (200, 70), color=(30, 30, 30))
        d = ImageDraw.Draw(img)
        # We would ideally load a proper font, using default here.
        
        for i in range(500):
            d.point((random.randint(0, 200), random.randint(0, 70)), fill=(random.randint(50, 255), random.randint(50, 255), random.randint(50, 255)))

        d.text((40, 20), text, fill=(255, 255, 255))
        
        # Draw some lines
        for _ in range(5):
            d.line([(random.randint(0, 200), random.randint(0, 70)), (random.randint(0, 200), random.randint(0, 70))], fill=(255, 255, 255), width=2)

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @staticmethod
    async def create_session(guild_id: int, user_id: int) -> tuple[str, BytesIO]:
        # Generate random 5 char string
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        
        # Save to Redis
        conn = RedisClient.redis_conn
        key = f"captcha:{guild_id}:{user_id}"
        await conn.hset(key, mapping={"code": code})
        await conn.expire(key, config.CAPTCHA_TIMEOUT_SECONDS)
        
        # Return image buffer
        return code, CaptchaService.generate_image(code)

    @staticmethod
    async def validate(guild_id: int, user_id: int, code: str) -> bool:
        conn = RedisClient.redis_conn
        key = f"captcha:{guild_id}:{user_id}"
        
        stored_code = await conn.hget(key, "code")
        if not stored_code:
            return False
            
        if stored_code.upper() == code.upper():
            await conn.delete(key)
            return True
        return False
