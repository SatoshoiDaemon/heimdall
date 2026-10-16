import asyncio
import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from time import perf_counter

import discord
from pymongo import ReturnDocument

from src.core.config import config
from src.core.database import Database, _session
from src.core.event_bus import EventBus
from src.core.metrics import counters, observe
from src.dtos.payloads import LogEventDTO

log = logging.getLogger("modbot.logworker")


class LogService:
    QUEUE_SIZE = 1000
    _queue: asyncio.Queue | None = None
    _scheduled: set[str] = set()

    @classmethod
    def reset_queue(cls):
        cls._queue = asyncio.Queue(maxsize=cls.QUEUE_SIZE)
        cls._scheduled = set()

    @classmethod
    def schedule(cls, event_id):
        if cls._queue is None:
            cls.reset_queue()
        if event_id in cls._scheduled:
            return
        try:
            cls._queue.put_nowait(event_id)
            cls._scheduled.add(event_id)
        except asyncio.QueueFull:
            # The record is already durable. The next scan will pick it up.
            counters["audit_queue_full"] += 1

    MAX_ATTEMPTS = 5

    @staticmethod
    async def enqueue_log(dto: LogEventDTO, event_id: str | None = None):
        # Mongo outbox is authoritative; the local queue is bounded and disposable.
        # Case transactions
        # write the outbox in the same transaction as their projections/state.
        event_id = event_id or uuid.uuid4().hex
        await Database.db.audit_outbox.update_one(
            {"_id": event_id},
            {
                "$setOnInsert": {
                    "payload": asdict(dto),
                    "delivered": False,
                    "attempts": 0,
                    "created_at": datetime.now(UTC),
                    "next_attempt": datetime.now(UTC),
                }
            },
            upsert=True,
            session=_session.get(),
        )
        LogService.schedule(event_id)
        return event_id

    @staticmethod
    async def _send(bot, event_id, payload):
        from src.services.config_service import ConfigService

        settings = await ConfigService.get_guild_config(payload["guild_id"])
        if not settings.log_channel_id:
            # Explicit disposition; enabling logs later does not replay history.
            return "unconfigured"
        channel = bot.get_channel(settings.log_channel_id)
        if channel is None:
            channel = await bot.fetch_channel(settings.log_channel_id)
        if getattr(channel.guild, "id", None) != payload["guild_id"]:
            raise ValueError("Audit channel belongs to another guild")
        embed = discord.Embed(
            title=payload["event_type"][:256],
            description=payload["description"][:3500],
            color=payload["color"],
        )
        embed.set_footer(
            text=f"Event {event_id} | Case {payload.get('case_number') or '-'} | Origin {(payload.get('metadata') or {}).get('origin', 'manual')}"
        )
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        return "sent"

    @staticmethod
    async def deliver(bot, event_id):
        now = datetime.now(UTC)
        token = uuid.uuid4().hex
        entry = await Database.db.audit_outbox.find_one_and_update(
            {
                "_id": event_id,
                "delivered": False,
                "attempts": {"$lt": LogService.MAX_ATTEMPTS},
                "next_attempt": {"$lte": now},
                "$or": [{"lease_until": {"$exists": False}}, {"lease_until": {"$lte": now}}],
            },
            {"$set": {"lease_until": now + timedelta(seconds=120), "lease_token": token}},
            return_document=ReturnDocument.AFTER,
        )
        if entry is None:
            return False
        started = perf_counter()
        try:
            # Bound delivery duration below its lease to prevent active consumers
            # overlapping. A crash after send/before ack can still duplicate.
            outcome = await asyncio.wait_for(
                LogService._send(bot, event_id, entry["payload"]), timeout=90
            )
        except Exception as error:
            attempts = entry["attempts"] + 1
            counters["audit_delivery_failed"] += 1
            await Database.db.audit_outbox.update_one(
                {"_id": event_id, "lease_token": token},
                {
                    "$set": {
                        "attempts": attempts,
                        "last_error": str(error)[:500],
                        "next_attempt": now + timedelta(seconds=min(300, 2**attempts)),
                        "dead": attempts >= LogService.MAX_ATTEMPTS,
                    },
                    "$unset": {"lease_until": "", "lease_token": ""},
                },
            )
            if attempts >= LogService.MAX_ATTEMPTS:
                await Database.db.audit_failures.update_one(
                    {"_id": event_id},
                    {
                        "$set": {
                            "payload": entry["payload"],
                            "error": str(error)[:500],
                            "attempts": attempts,
                        }
                    },
                    upsert=True,
                )
            log.exception(
                "Audit delivery failed",
                extra={
                    "guild_id": entry["payload"]["guild_id"],
                    "case_id": entry["payload"].get("case_number"),
                    "action": "audit",
                    "outcome": "retry",
                },
            )
            return False
        await Database.db.audit_outbox.update_one(
            {"_id": event_id, "lease_token": token},
            {
                "$set": {"delivered": True, "outcome": outcome, "delivered_at": datetime.now(UTC)},
                "$unset": {"lease_until": "", "lease_token": ""},
            },
        )
        observe("audit_delivered", started)
        return True

    @staticmethod
    async def run_once(bot):
        if LogService._queue is None:
            LogService.reset_queue()
        now = datetime.now(UTC)
        available = LogService.QUEUE_SIZE - len(LogService._scheduled)
        if available > 0:
            docs = (
                await Database.db.audit_outbox.find(
                    {
                        "delivered": False,
                        "attempts": {"$lt": LogService.MAX_ATTEMPTS},
                        "next_attempt": {"$lte": now},
                        "$or": [
                            {"lease_until": {"$exists": False}},
                            {"lease_until": {"$lte": now}},
                        ],
                    },
                    {"_id": 1},
                )
                .sort("next_attempt", 1)
                .limit(min(available, 100))
                .to_list(length=min(available, 100))
            )
            for entry in docs:
                LogService.schedule(entry["_id"])
        for _ in range(20):
            try:
                event_id = LogService._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                await LogService.deliver(bot, event_id)
            finally:
                LogService._scheduled.discard(event_id)
                LogService._queue.task_done()
        counters["audit_pending"] = await Database.db.audit_outbox.count_documents(
            {"delivered": False, "dead": {"$ne": True}}
        )
        counters["audit_dead"] = await Database.db.audit_outbox.count_documents({"dead": True})
        counters["audit_queue_size"] = LogService._queue.qsize()

    @staticmethod
    async def worker(bot):
        await bot.wait_until_ready()
        while not bot.is_closed():
            if bot.is_ready():
                try:
                    await LogService.run_once(bot)
                except Exception:
                    log.exception("Audit worker unavailable; Mongo records retained for retry")
            await asyncio.sleep(config.LOG_WORKER_INTERVAL_SECONDS)


EventBus.subscribe("audit_log", LogService.enqueue_log)
