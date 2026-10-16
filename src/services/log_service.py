import asyncio
import json
import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from time import perf_counter

import discord
from pymongo import ReturnDocument
from redis.exceptions import ResponseError

from src.core.config import config
from src.core.database import Database, _session
from src.core.event_bus import EventBus
from src.core.metrics import counters, observe
from src.core.redis_client import RedisClient
from src.dtos.payloads import LogEventDTO

log = logging.getLogger("modbot.logworker")


class LogService:
    QUEUE_KEY = "modbot:audit"
    GROUP = "delivery"
    MAX_ATTEMPTS = 5

    @staticmethod
    async def enqueue_log(dto: LogEventDTO, event_id: str | None = None):
        # Mongo outbox is durable even if Redis is unavailable. Case transactions
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
        embed.set_footer(text=f"Event {event_id} | Case {payload.get('case_number') or '-'}")
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
    async def migrate_legacy():
        """Atomically wrap old list entries with IDs before claiming them."""
        conn = RedisClient.redis_conn
        processing = "modbot:log_queue:migrating"
        for _ in range(20):
            item = await conn.lindex(processing, -1)
            if item is None:
                item = await conn.eval(
                    """
                    local raw = redis.call('RPOP', KEYS[1])
                    if not raw then return false end
                    local wrapped = ARGV[1] .. ':' .. raw
                    redis.call('LPUSH', KEYS[2], wrapped)
                    return wrapped
                """,
                    2,
                    "modbot:log_queue",
                    processing,
                    uuid.uuid4().hex,
                )
            if not item:
                return
            try:
                event_id, raw = item.split(":", 1)
                dto = LogEventDTO(**json.loads(raw))
            except (ValueError, TypeError, KeyError):
                await conn.lpush("modbot:legacy_log_failures", item)
                await conn.lrem(processing, 1, item)
                log.error("Malformed legacy audit entry preserved in Redis failure queue")
                continue
            await LogService.enqueue_log(dto, event_id=event_id)
            await conn.lrem(processing, 1, item)

    @staticmethod
    async def run_once(bot, consumer):
        conn = RedisClient.redis_conn
        await LogService.migrate_legacy()
        try:
            await conn.xgroup_create(LogService.QUEUE_KEY, LogService.GROUP, id="0", mkstream=True)
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise
        now = datetime.now(UTC)
        # Re-mirror unconfirmed entries after restarts or Redis data loss.
        docs = (
            await Database.db.audit_outbox.find(
                {
                    "delivered": False,
                    "attempts": {"$lt": LogService.MAX_ATTEMPTS},
                    "next_attempt": {"$lte": now},
                    "$or": [
                        {"queued_at": {"$exists": False}},
                        {"queued_at": {"$lte": now - timedelta(seconds=60)}},
                    ],
                }
            )
            .limit(20)
            .to_list(length=20)
        )
        for entry in docs:
            await conn.xadd(LogService.QUEUE_KEY, {"event_id": entry["_id"]})
            await Database.db.audit_outbox.update_one(
                {"_id": entry["_id"]}, {"$set": {"queued_at": now}}
            )
        recovered = await conn.xautoclaim(
            LogService.QUEUE_KEY, LogService.GROUP, consumer, 60000, count=20
        )
        messages = list(recovered[1])
        fresh = await conn.xreadgroup(
            LogService.GROUP, consumer, {LogService.QUEUE_KEY: ">"}, count=20
        )
        for _, batch in fresh:
            messages.extend(batch)
        for stream_id, fields in messages:
            await LogService.deliver(bot, fields["event_id"])
            state = await Database.db.audit_outbox.find_one({"_id": fields["event_id"]})
            # Retry scheduling is durable in Mongo before stream acknowledgment.
            if state and (state.get("delivered") or not state.get("lease_until")):
                await conn.xack(LogService.QUEUE_KEY, LogService.GROUP, stream_id)
                await conn.xdel(LogService.QUEUE_KEY, stream_id)
        counters["audit_pending"] = await Database.db.audit_outbox.count_documents(
            {"delivered": False, "dead": {"$ne": True}}
        )
        counters["audit_dead"] = await Database.db.audit_outbox.count_documents({"dead": True})

    @staticmethod
    async def worker(bot):
        await bot.wait_until_ready()
        consumer = uuid.uuid4().hex
        while not bot.is_closed():
            try:
                await LogService.run_once(bot, consumer)
            except Exception:
                log.exception("Audit worker unavailable; durable outbox retained")
            await asyncio.sleep(config.LOG_WORKER_INTERVAL_SECONDS)


EventBus.subscribe("audit_log", LogService.enqueue_log)
