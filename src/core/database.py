import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

from src.core.config import config

_session = ContextVar("mongo_session", default=None)
_commit_callbacks = ContextVar("commit_callbacks", default=None)

log = logging.getLogger("modbot.database")


class Database:
    client: AsyncIOMotorClient = None
    db = None
    transactions_supported = False

    @classmethod
    async def connect(cls):
        log.info("Connecting to MongoDB...")
        cls.client = AsyncIOMotorClient(
            config.MONGO_URI, tz_aware=True, serverSelectionTimeoutMS=10000
        )
        cls.db = cls.client[config.MONGO_DB_NAME]
        hello = await cls.db.command("hello")
        cls.transactions_supported = bool(hello.get("setName") or hello.get("msg") == "isdbgrid")
        await cls.ensure_indexes()
        await cls.db.cases.update_many(
            {"status": {"$exists": False}}, {"$set": {"status": "completed", "origin": "manual"}}
        )
        log.info("MongoDB connected successfully.")

    @classmethod
    async def close(cls):
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None
            log.info("MongoDB connection closed.")

    @classmethod
    async def ensure_indexes(cls):
        await cls.db.captcha_sessions.create_index("expires_at", expireAfterSeconds=0)
        await cls.db.audit_outbox.create_index([("delivered", 1), ("next_attempt", 1)])
        await cls.db.rbac.create_index(
            [("guild_id", 1), ("type", 1), ("role_id", 1), ("user_id", 1)], unique=True
        )
        await cls.db.audit_outbox.create_index([("delivered", 1), ("attempts", 1)])
        await cls.db.cases.create_index([("status", 1), ("created_at", 1)])
        await cls.db.cases.create_index(
            [("operation_id", 1)],
            unique=True,
            partialFilterExpression={"operation_id": {"$type": "string"}},
        )
        for collection in (cls.db.warns, cls.db.notes, cls.db.punishments):
            await collection.create_index(
                [("guild_id", 1), ("case_number", 1)],
                unique=True,
                partialFilterExpression={"case_number": {"$type": "number"}},
            )
        # Mandatory Indexes
        await cls.db.warns.create_index([("guild_id", 1), ("user_id", 1)])
        await cls.db.notes.create_index([("guild_id", 1), ("user_id", 1)])
        await cls.db.punishments.create_index([("guild_id", 1), ("user_id", 1), ("active", 1)])
        await cls.db.configs.create_index([("guild_id", 1)], unique=True)
        await cls.db.cases.create_index([("guild_id", 1), ("case_number", 1)], unique=True)
        await cls.db.cases.create_index(
            [("guild_id", 1), ("target_user_id", 1), ("created_at", -1)]
        )
        await cls.db.case_counters.create_index([("guild_id", 1)], unique=True)

    @classmethod
    async def next_case_number(cls, guild_id: int) -> int:
        counter = await cls.db.case_counters.find_one_and_update(
            {"guild_id": guild_id},
            {"$inc": {"next_case_number": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
            session=_session.get(),
        )
        return int(counter["next_case_number"])

    @staticmethod
    def after_commit(callback):
        callbacks = _commit_callbacks.get()
        if callbacks is not None:
            callbacks.append(callback)

    @classmethod
    @asynccontextmanager
    async def transaction(cls):
        """Use transactions on replica sets; standalone recovers from durable cases."""
        if not cls.transactions_supported or _session.get() is not None:
            yield
            return
        callbacks = []
        callback_token = _commit_callbacks.set(callbacks)
        try:
            async with await cls.client.start_session() as session:
                async with session.start_transaction():
                    token = _session.set(session)
                    try:
                        yield
                    finally:
                        _session.reset(token)
        finally:
            _commit_callbacks.reset(callback_token)
            # Invalidate after commit OR rollback: cache cannot retain a value
            # read while the transaction was still pending.
            for callback in callbacks:
                callback()
