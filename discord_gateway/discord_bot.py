"""
discord_gateway/discord_bot.py
──────────────────────────────
Discord Voice Dispatch Bot — Integrated RoIP Gateway.

Runs as an asyncio background task inside the FastAPI process (no separate port).
Consumes DispatchPayload items from the shared audio_queue and plays them
in a Discord voice channel using FFmpegPCMAudio.

Integration:
    - Started via `start_discord_bot()` in the FastAPI lifespan.
    - Stopped via `stop_discord_bot()` on shutdown.
    - Audio arrives through `app.core.audio_queue.audio_queue`.

Dependencies:
    pip install discord.py PyNaCl
"""

import asyncio
import logging
import os

import discord

from app.config import settings
from app.core.audio_queue import audio_queue, DispatchPayload

logger = logging.getLogger("discord_gateway")

# ── Discord Bot Setup ─────────────────────────────────────────────────────────
intents = discord.Intents.default()
# intents.message_content = True  # Removed: Causes PrivilegedIntentsRequired crash if not enabled in Developer Portal

bot = discord.Client(intents=intents)

# Background task reference for the queue consumer
_consumer_task: asyncio.Task | None = None


# ── Audio Playback Helper ─────────────────────────────────────────────────────
async def play_audio_in_voice_channel(file_path: str, unit_code: str) -> None:
    """
    Connects to the configured voice channel, plays the audio file,
    waits for playback to finish, then disconnects.
    """
    channel_id = settings.discord_voice_channel_id
    channel = bot.get_channel(channel_id)

    if channel is None:
        logger.error(
            "Voice channel with ID %s not found. "
            "Check DISCORD_VOICE_CHANNEL_ID and that the bot has access to the server.",
            channel_id,
        )
        return

    if not isinstance(channel, discord.VoiceChannel):
        logger.error("Channel ID %s is not a voice channel.", channel_id)
        return

    vc: discord.VoiceClient | None = None
    try:
        logger.info("Connecting to voice channel: %s", channel.name)
        vc = await channel.connect()

        logger.info("Playing TTS alert for unit: %s | file: %s", unit_code, file_path)
        audio_source = discord.FFmpegPCMAudio(file_path)
        vc.play(audio_source)

        # Wait until playback finishes before disconnecting
        while vc.is_playing():
            await asyncio.sleep(0.5)

        logger.info("Playback complete for unit: %s", unit_code)

    except discord.ClientException as exc:
        logger.exception("Discord client error during voice playback: %s", exc)
    except Exception as exc:
        logger.exception("Unexpected error during voice playback: %s", exc)
    finally:
        if vc and vc.is_connected():
            await vc.disconnect()
            logger.info("Disconnected from voice channel.")

        # Always clean up the temp audio file
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info("Temp audio file deleted: %s", file_path)


# ── Queue Consumer (replaces the aiohttp web server) ─────────────────────────
async def _queue_consumer() -> None:
    """
    Continuously consumes DispatchPayload items from the shared audio_queue.
    Each item triggers voice channel playback. Runs until cancelled.
    """
    logger.info("[BOT] Queue consumer started — waiting for audio dispatches...")
    while True:
        try:
            payload: DispatchPayload = await audio_queue.get()
            logger.info(
                "[BOT] Dequeued audio dispatch | unit=%s ambulance=%s trigger=%s",
                payload.unit_code,
                payload.ambulance_id,
                payload.trigger_type,
            )
            await play_audio_in_voice_channel(payload.file_path, payload.unit_code)
            audio_queue.task_done()
        except asyncio.CancelledError:
            logger.info("[BOT] Queue consumer cancelled.")
            break
        except Exception as exc:
            logger.exception("[BOT] Error processing audio dispatch: %s", exc)


# ── Discord Bot Events ────────────────────────────────────────────────────────
@bot.event
async def on_ready() -> None:
    global _consumer_task
    logger.info(
        "[BOT] Logged in as %s (id=%s) | Guilds: %d",
        bot.user, bot.user.id, len(bot.guilds),
    )
    logger.info("[BOT] Ready to receive RoIP dispatches via in-process queue.")

    # Start the queue consumer once the bot is connected and ready
    if _consumer_task is None or _consumer_task.done():
        _consumer_task = asyncio.create_task(_queue_consumer())


# ── Lifecycle Helpers (called from FastAPI lifespan) ──────────────────────────
async def start_discord_bot() -> None:
    """
    Start the Discord bot. This coroutine blocks until the bot disconnects,
    so it should be wrapped in asyncio.create_task().
    """
    token = settings.discord_bot_token
    if not token:
        logger.warning(
            "⚠️  DISCORD_BOT_TOKEN is empty — Discord RoIP gateway will NOT start. "
            "Voice alerts will be silently skipped."
        )
        return

    logger.info("[BOT] Starting Discord bot...")
    try:
        await bot.start(token)
    except Exception as exc:
        logger.exception("[BOT] Discord bot crashed: %s", exc)


async def stop_discord_bot() -> None:
    """Gracefully close the Discord bot and cancel the queue consumer."""
    global _consumer_task
    if _consumer_task and not _consumer_task.done():
        _consumer_task.cancel()
        _consumer_task = None

    if not bot.is_closed():
        logger.info("[BOT] Shutting down Discord bot...")
        await bot.close()
        logger.info("[BOT] Discord bot closed.")
