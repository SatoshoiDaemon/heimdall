from motor.motor_asyncio import AsyncIOMotorClient
from src.core.config import config
import logging

log = logging.getLogger("modbot.database")

class Database:
    client: AsyncIOMotorClient = None
    db = None

    @classmethod
    async def connect(cls):
        log.info(f"Connecting to MongoDB...")
        cls.client = AsyncIOMotorClient(config.MONGO_URI)
        cls.db = cls.client[config.MONGO_DB_NAME]
        await cls.ensure_indexes()
        log.info("MongoDB connected successfully.")

    @classmethod
    async def close(cls):
        if cls.client:
            cls.client.close()
            log.info("MongoDB connection closed.")

    @classmethod
    async def ensure_indexes(cls):
        # Mandatory Indexes
        await cls.db.warns.create_index([("guild_id", 1), ("user_id", 1)])
        await cls.db.notes.create_index([("guild_id", 1), ("user_id", 1)])
        await cls.db.punishments.create_index([("guild_id", 1), ("user_id", 1), ("active", 1)])
        await cls.db.configs.create_index([("guild_id", 1)], unique=True)
