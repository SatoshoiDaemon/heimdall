import asyncio
import json
import logging
from src.core.redis_client import RedisClient
from src.dtos.payloads import LogEventDTO
from src.core.config import config
from src.core.event_bus import EventBus
import discord
from discord.ext import commands

log = logging.getLogger("modbot.logworker")

class LogService:
    QUEUE_KEY = "modbot:log_queue"

    @staticmethod
    async def enqueue_log(dto: LogEventDTO):
        conn = RedisClient.redis_conn
        await conn.lpush(LogService.QUEUE_KEY, json.dumps(dto.__dict__))

    @staticmethod
    async def worker(bot: commands.AutoShardedBot):
        log.info("Starting Background Log Worker...")
        # Since this relies on resolving channels via Bot, run in a while loop
        conn = RedisClient.redis_conn
        
        while not bot.is_closed():
            try:
                # Pop batch of logs
                log_entries = []
                while len(log_entries) < 20:
                    item = await conn.rpop(LogService.QUEUE_KEY)
                    if not item:
                        break
                    log_entries.append(json.loads(item))

                if log_entries:
                    await LogService._process_batch(bot, log_entries)
                
                await asyncio.sleep(config.LOG_WORKER_INTERVAL_SECONDS)
            except Exception as e:
                log.error(f"Log worker error: {e}")
                await asyncio.sleep(5)

    @staticmethod
    async def _process_batch(bot, entries):
        # Group entries by guild to resolve config efficiently
        # Since Services are stateless, they must resolve settings dynamically
        from src.services.config_service import ConfigService 
        # inline import to avoid circular dependency
        
        guilds_map = {}
        for entry in entries:
            gid = entry['guild_id']
            if gid not in guilds_map:
                guilds_map[gid] = []
            guilds_map[gid].append(entry)
            
        for gid, log_batch in guilds_map.items():
            g_config = await ConfigService.get_guild_config(gid)
            if not g_config or not g_config.log_channel_id:
                continue
                
            guild = bot.get_guild(gid)
            if not guild:
                continue
                
            channel = guild.get_channel(g_config.log_channel_id)
            if not channel:
                continue

            # Batch send
            embeds = []
            for item in log_batch:
                embed = discord.Embed(
                    title=item['event_type'], 
                    description=item['description'], 
                    color=item['color']
                )
                if item.get('moderator_id'):
                    embed.set_footer(text=f"Mod ID: {item['moderator_id']}")
                if item.get('case_number'):
                    embed.set_footer(text=f"Case #{item['case_number']} | Mod ID: {item.get('moderator_id', 'n/a')}")
                embeds.append(embed)
            
            # Send up to 10 embeds per message (Discord limit)
            for i in range(0, len(embeds), 10):
                await channel.send(embeds=embeds[i:i+10])
                await asyncio.sleep(0.5)

# Subscribe the enqueue function to EventBus natively
EventBus.subscribe("audit_log", LogService.enqueue_log)
