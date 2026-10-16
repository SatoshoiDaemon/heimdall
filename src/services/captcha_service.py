import hmac
import random
import secrets
import string
from io import BytesIO

import discord
from PIL import Image, ImageDraw

from src.core.config import config
from src.core.exceptions import ModerationError
from src.core.redis_client import RedisClient
from src.services.config_service import ACCESS_PERMISSIONS, ConfigService
from src.services.lock_service import LockService


class CaptchaService:
    @staticmethod
    def generate_image(text: str) -> BytesIO:
        # Simple captcha image generator
        img = Image.new("RGB", (200, 70), color=(30, 30, 30))
        d = ImageDraw.Draw(img)
        # We would ideally load a proper font, using default here.

        for _ in range(500):
            d.point(
                (random.randint(0, 200), random.randint(0, 70)),
                fill=(random.randint(50, 255), random.randint(50, 255), random.randint(50, 255)),
            )

        d.text((40, 20), text, fill=(255, 255, 255))

        # Draw some lines
        for _ in range(5):
            d.line(
                [
                    (random.randint(0, 200), random.randint(0, 70)),
                    (random.randint(0, 200), random.randint(0, 70)),
                ],
                fill=(255, 255, 255),
                width=2,
            )

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @staticmethod
    async def create_session(guild_id: int, user_id: int) -> tuple[str, BytesIO]:
        # Generate random 5 char string
        code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))

        # Save to Redis
        conn = RedisClient.redis_conn
        key = f"captcha:{guild_id}:{user_id}"
        async with LockService.get_lock(f"lock:captcha:{guild_id}:{user_id}"):
            async with conn.pipeline(transaction=True) as pipe:
                pipe.hset(key, mapping={"code": code})
                pipe.expire(key, config.CAPTCHA_TIMEOUT_SECONDS)
                await pipe.execute()

        # Return image buffer
        return code, CaptchaService.generate_image(code)

    @staticmethod
    async def validate(guild_id: int, user_id: int, code: str) -> bool:
        """Check without consuming: completion owns the session lifecycle."""
        stored = await RedisClient.redis_conn.hget(f"captcha:{guild_id}:{user_id}", "code")
        return bool(stored and hmac.compare_digest(stored.upper(), code.strip().upper()))

    @staticmethod
    async def complete(guild: discord.Guild, member: discord.Member, code: str) -> bool:
        async with LockService.get_lock(f"lock:captcha:{guild.id}:{member.id}"):
            settings = await ConfigService.get_guild_config(guild.id)
            role = guild.get_role(settings.verified_role_id) if settings.verified_role_id else None
            if role is None or role.is_default() or role.managed:
                raise ModerationError("Configure an existing, assignable verified role first.")
            safe = ACCESS_PERMISSIONS
            if role.permissions.value & ~safe:
                raise ModerationError("Verified roles must not grant elevated permissions.")
            if not await CaptchaService.validate(guild.id, member.id, code):
                return False
            if role not in member.roles:
                if not guild.me.guild_permissions.manage_roles or role >= guild.me.top_role:
                    raise ModerationError(
                        "Heimdall needs Manage Roles and a role above the verified role."
                    )
                try:
                    await member.add_roles(role, reason="CAPTCHA verification")
                except discord.HTTPException as error:
                    raise ModerationError(
                        "Role assignment failed. You can retry the same CAPTCHA before it expires."
                    ) from error
            # add_roles succeeded (or the role was already present). A crash before
            # this delete is recoverable: retry observes the role and consumes once.
            await RedisClient.redis_conn.eval(
                "if redis.call('hget',KEYS[1],'code') == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",
                1,
                f"captcha:{guild.id}:{member.id}",
                code.strip().upper(),
            )
            return True
