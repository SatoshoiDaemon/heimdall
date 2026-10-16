import hashlib
import hmac
import random
import secrets
import string
from datetime import UTC, datetime, timedelta
from io import BytesIO

import discord
from PIL import Image, ImageDraw

from src.core.config import config
from src.core.database import Database
from src.core.exceptions import ModerationError
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

    MAX_ATTEMPTS = 5

    @staticmethod
    async def create_session(guild_id: int, user_id: int) -> tuple[str, BytesIO]:
        code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        async with LockService.get_lock(f"lock:captcha:{guild_id}:{user_id}"):
            await Database.db.captcha_sessions.replace_one(
                {"_id": f"{guild_id}:{user_id}"},
                {
                    "_id": f"{guild_id}:{user_id}",
                    "code_hash": hashlib.sha256(code.encode()).hexdigest(),
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "attempts": 0,
                    "consumed": False,
                    "expires_at": datetime.now(UTC)
                    + timedelta(seconds=config.CAPTCHA_TIMEOUT_SECONDS),
                },
                upsert=True,
            )
        return code, CaptchaService.generate_image(code)

    @staticmethod
    async def validate(guild_id: int, user_id: int, code: str) -> bool:
        """Expiration is checked here; the Mongo TTL index only cleans storage."""
        key = f"{guild_id}:{user_id}"
        session = await Database.db.captcha_sessions.find_one(
            {
                "_id": key,
                "consumed": False,
                "expires_at": {"$gt": datetime.now(UTC)},
                "attempts": {"$lt": CaptchaService.MAX_ATTEMPTS},
            }
        )
        if session is None:
            return False
        digest = hashlib.sha256(code.strip().upper().encode()).hexdigest()
        if hmac.compare_digest(session["code_hash"], digest):
            return True
        await Database.db.captcha_sessions.update_one({"_id": key}, {"$inc": {"attempts": 1}})
        return False

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
            await Database.db.captcha_sessions.update_one(
                {"_id": f"{guild.id}:{member.id}"},
                {"$set": {"consumed": True, "verified_role_id": role.id}},
            )
            return True
