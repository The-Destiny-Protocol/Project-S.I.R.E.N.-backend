"""
discord_gateway/discord_bot.py
──────────────────────────────
Standalone Discord Voice Dispatch Bot — Mock RoIP Gateway.

Acts as the Radio-over-IP (RoIP) gateway for the FastAPI backend.
Receives a .wav audio alert via HTTP (from roip_service.py), plays it
in a Discord voice channel, then disconnects cleanly.

Architecture:
  - aiohttp web server  →  listens on port 8001 for audio dispatch requests
  - discord.py bot      →  connects to a voice channel and plays the audio

Run this bot standalone:
    py discord_gateway/discord_bot.py

Dependencies:
    pip install discord.py aiohttp PyNaCl
"""

import asyncio
import logging
import os
import tempfile
import uuid

import aiohttp
from aiohttp import web

import discord

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — fill these in before running
# ─────────────────────────────────────────────────────────────────────────────

# Your Discord Bot token from https://discord.com/developers/applications
DISCORD_TOKEN: str = "MTUzNDg1NTY4NDI1MDc5NjEwNA.GPGyTI.G8CHqy-DinJZen_JQYvmHb2G8kUGX3wZ6_Jh6I"

# The ID of the Voice Channel the bot should join to play the alert.
# Right-click a voice channel in Discord → Copy Channel ID (enable Developer Mode first)
VOICE_CHANNEL_ID: int = 1534858284194856960

# The aiohttp web server will listen on this port.
# NOTE: Update ROIP_GATEWAY_URL in app/services/roip_service.py to:
#       http://localhost:8001/api/v1/emergency/mock-roip-gateway
WEB_SERVER_PORT: int = 8001

# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("discord_gateway")

# ── Discord Bot Setup ─────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True  # required for some gateway events

bot = discord.Client(intents=intents)


# ── Audio Playback Helper ─────────────────────────────────────────────────────
async def play_audio_in_voice_channel(file_path: str, unit_code: str) -> None:
    """
    Connects to the configured voice channel, plays the .wav file,
    waits for playback to finish, then disconnects.
    """
    channel = bot.get_channel(VOICE_CHANNEL_ID)

    if channel is None:
        logger.error(
            "Voice channel with ID %s not found. "
            "Check VOICE_CHANNEL_ID and that the bot has access to the server.",
            VOICE_CHANNEL_ID,
        )
        return

    if not isinstance(channel, discord.VoiceChannel):
        logger.error("Channel ID %s is not a voice channel.", VOICE_CHANNEL_ID)
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


# ── aiohttp Web Server ────────────────────────────────────────────────────────
async def handle_roip_dispatch(request: web.Request) -> web.Response:
    """
    POST /api/v1/emergency/mock-roip-gateway

    Accepts:
        Multipart form-data with:
          - audio   : .wav audio file bytes
          - unit_code : police unit call-sign string

    OR raw audio/wav body with custom headers:
          - X-Police-Unit : police unit call-sign
          - X-Ambulance-Id: ambulance UUID
          - X-Trigger-Type: trigger source string
    """
    content_type = request.content_type or ""
    unit_code = "UNKNOWN"
    tmp_path = os.path.join(tempfile.gettempdir(), f"discord_roip_{uuid.uuid4().hex}.wav")

    try:
        # ── Multipart form-data (from a form or test client) ──────────────────
        if "multipart" in content_type:
            reader = await request.multipart()
            async for part in reader:
                if part.name == "unit_code":
                    unit_code = (await part.read()).decode("utf-8", errors="replace")
                elif part.name == "audio":
                    audio_data = await part.read()
                    with open(tmp_path, "wb") as f:
                        f.write(audio_data)

        # ── Raw audio/wav body (from roip_service.py httpx dispatch) ─────────
        else:
            unit_code = request.headers.get("X-Police-Unit", "UNKNOWN")
            ambulance_id = request.headers.get("X-Ambulance-Id", "UNKNOWN")
            trigger = request.headers.get("X-Trigger-Type", "UNKNOWN")
            audio_data = await request.read()

            with open(tmp_path, "wb") as f:
                f.write(audio_data)

            logger.info(
                "[GATEWAY] Raw audio received | unit=%s ambulance=%s trigger=%s size=%d bytes",
                unit_code, ambulance_id, trigger, len(audio_data),
            )

        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            logger.warning("[GATEWAY] Empty or missing audio payload — skipping playback.")
            return web.json_response(
                {"status": "error", "message": "Empty audio payload received."},
                status=400,
            )

        logger.info(
            "[GATEWAY] Audio dispatch received for unit=%s | size=%d bytes | queuing playback ...",
            unit_code, os.path.getsize(tmp_path),
        )

        # Schedule voice playback as a background coroutine so we return HTTP 200 immediately
        asyncio.create_task(play_audio_in_voice_channel(tmp_path, unit_code))

        return web.json_response({
            "status": "received",
            "gateway": "discord-roip",
            "police_unit": unit_code,
            "audio_size_bytes": os.path.getsize(tmp_path),
            "message": "Audio queued for voice channel playback.",
        })

    except Exception as exc:
        logger.exception("[GATEWAY] Failed to handle dispatch request: %s", exc)
        # Clean up temp file on error
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return web.json_response(
            {"status": "error", "message": str(exc)},
            status=500,
        )


async def start_web_server() -> None:
    """Start the aiohttp web server in the background."""
    app = web.Application(client_max_size=1024**2 * 10)
    app.router.add_post("/api/v1/emergency/mock-roip-gateway", handle_roip_dispatch)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=WEB_SERVER_PORT)
    await site.start()
    logger.info(
        "[GATEWAY] aiohttp web server started on http://0.0.0.0:%d/api/v1/emergency/mock-roip-gateway",
        WEB_SERVER_PORT,
    )


# ── Discord Bot Events ────────────────────────────────────────────────────────
@bot.event
async def on_ready() -> None:
    logger.info(
        "[BOT] Logged in as %s (id=%s) | Guilds: %d",
        bot.user, bot.user.id, len(bot.guilds),
    )
    logger.info("[BOT] Ready to receive RoIP dispatches on port %d.", WEB_SERVER_PORT)


# ── Entrypoint ────────────────────────────────────────────────────────────────
async def main() -> None:
    """
    Start both the Discord bot and the aiohttp web server concurrently
    using a single asyncio event loop.
    """
    async with bot:
        # Launch the web server as a background task before the bot connects
        await start_web_server()
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
