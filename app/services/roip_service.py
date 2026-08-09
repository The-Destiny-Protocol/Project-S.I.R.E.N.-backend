"""
app/services/roip_service.py
────────────────────────────
Google Text-to-Speech (gTTS) synthesis + Radio-over-IP (RoIP) dispatch service.

Flow:
  1. Compose an urgent voice alert message.
  2. Synthesize it to a temporary .mp3 file using gTTS (natural AI voice).
  3. POST the .mp3 bytes to the configured RoIP gateway via httpx.AsyncClient.
  4. Clean up the temp file regardless of success or failure.

⚠️  gTTS performs a synchronous HTTP request to fetch the audio. To avoid blocking 
   the FastAPI event loop, synthesis is wrapped in asyncio.to_thread().
"""

import asyncio
import logging
import os
import tempfile
import uuid

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Fallback check for DISCORD_WEBHOOK_URL (Text notifications)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
if not DISCORD_WEBHOOK_URL:
    logger.warning("⚠️  _WEBHOOK_URL is missing or empty. Text alerts will not be sent to Discord.")
else:
    logger.info("✅ DISCORD_WEBHOOK_URL loaded successfully.")

# Target RoIP gateway — the Discord bot's aiohttp server (port 8001).
ROIP_GATEWAY_URL = "http://discord-gateway:8001/api/v1/emergency/mock-roip-gateway"


def _synthesize_tts_file(message: str, output_path: str) -> None:
    """
    Synthesizes speech using Google Text-to-Speech (gTTS).
    Configured with 'en' language and 'co.in' TLD for a natural Indian English accent.
    """
    from gtts import gTTS  # lazy import

    tts = gTTS(text=message, lang="en", tld="co.in", slow=False)
    tts.save(output_path)


async def generate_and_dispatch_audio(
    ambulance_id: str,
    vehicle_number: str,
    trigger_type: str,
    police_unit_code: str = "UNKNOWN",
    driver_name: str = "Unknown",
    contact_number: str = "Unknown",
    location_name: str = "an unknown location",
    destination_name: str | None = None,
    radio_channel_id: str | None = None,
) -> None:
    """
    Async entry point used by BackgroundTasks in the SOS endpoint.

    1. Builds a clear, urgent radio-ready alert message.
    2. Synthesizes to a temp .mp3 via gTTS (in a thread pool worker).
    3. POSTs the audio bytes to the RoIP gateway.
    4. Deletes the temp file.
    """
    print(
        f"[RoIP] >> Background TTS task STARTED | unit={police_unit_code} ambulance={ambulance_id} trigger={trigger_type}",
        flush=True,
    )
    logger.info(
        "🔊  [RoIP] Background TTS task started | unit=%s ambulance=%s trigger=%s",
        police_unit_code,
        ambulance_id,
        trigger_type,
    )

    if trigger_type == "GREEN_CORRIDOR":
        dest_phrase = f"en route to {destination_name}" if destination_name else "en route to its destination"
        message = (
            f"Traffic Control Alert. Green corridor preemption activated at intersection {location_name}. "
            f"Approaching vehicle {vehicle_number}, {dest_phrase}. All cross-traffic please hold. Over."
        )
    else:
        channel_info = f"on channel {radio_channel_id}" if radio_channel_id else ""
        trigger_label = (
            "DRIVER PANIC BUTTON ACTIVATED"
            if trigger_type == "MANUAL_DRIVER_SOS"
            else "AI VISION ANOMALY DETECTED -- AUTOMATIC SOS"
        )
        message = (
            f"URGENT. URGENT. URGENT. "
            f"Emergency alert for unit {police_unit_code} {channel_info}. "
            f"{trigger_label}. "
            f"Driver {driver_name} with Ambulance {vehicle_number} is blocked near {location_name} and requires immediate corridor clearance. "
            f"Please respond. Over."
        )

    tmp_path = os.path.join(tempfile.gettempdir(), f"roip_{uuid.uuid4().hex}.mp3")
    print(f"[RoIP] Synthesizing speech -> {tmp_path}", flush=True)
    logger.info("🔊  Synthesizing TTS alert → %s", tmp_path)

    try:
        # Run blocking gTTS fetch in a thread pool to avoid blocking the event loop
        await asyncio.to_thread(_synthesize_tts_file, message, tmp_path)

        print("[RoIP] OK TTS synthesis complete. Dispatching to gateway ...", flush=True)
        logger.info("🔊  TTS synthesis complete. Dispatching to RoIP gateway …")

        # Send text webhook if configured
        if DISCORD_WEBHOOK_URL:
            try:
                await client.post(DISCORD_WEBHOOK_URL, json={"content": f"🚨 **RoIP Dispatch:** {message}"})
            except Exception as e:
                logger.error("Failed to send text webhook: %s", e)

        # POST the .mp3 bytes to the gateway
        with open(tmp_path, "rb") as audio_file:
            audio_bytes = audio_file.read()

        print(f"[RoIP] Sending {len(audio_bytes)} bytes to {ROIP_GATEWAY_URL}", flush=True)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                ROIP_GATEWAY_URL,
                content=audio_bytes,
                headers={
                    "Content-Type": "audio/mpeg",
                    "X-Police-Unit": police_unit_code,
                    "X-Ambulance-Id": ambulance_id,
                    "X-Trigger-Type": trigger_type,
                    "X-Driver-Phone": contact_number,
                },
            )
            response.raise_for_status()
            print(f"[RoIP] OK Gateway response: {response.status_code}", flush=True)
            logger.info(
                "✅  TTS audio dispatched → mock gateway | status=%s | unit=%s",
                response.status_code,
                police_unit_code,
            )

    except Exception as exc:
        print(f"[RoIP] ERROR Dispatch FAILED: {exc}", flush=True)
        logger.exception("❌  RoIP dispatch failed for ambulance %s: %s", ambulance_id, exc)
    finally:
        # Always clean up the temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            print(f"[RoIP] DONE Temp file deleted: {tmp_path}", flush=True)
            logger.debug("🗑️   Temp audio file deleted: %s", tmp_path)