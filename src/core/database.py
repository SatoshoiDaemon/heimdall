from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from src.core.config import config
import logging

log = logging.getLogger("modbot.database")

class Database:
    client: AsyncIOMotorClient = None
    db = None

    @classmethod
    async def connect(cls):
        log.info("Connecting to MongoDB...")
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
        await cls.db.cases.create_index([("guild_id", 1), ("case_number", 1)], unique=True)
        await cls.db.cases.create_index([("guild_id", 1), ("target_user_id", 1), ("created_at", -1)])
        await cls.db.case_counters.create_index([("guild_id", 1)], unique=True)

    @classmethod
    async def next_case_number(cls, guild_id: int) -> int:
        counter = await cls.db.case_counters.find_one_and_update(
            {"guild_id": guild_id},
            {"$inc": {"next_case_number": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(counter["next_case_number"])
