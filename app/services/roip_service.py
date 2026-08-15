"""
app/services/roip_service.py
────────────────────────────
Google Text-to-Speech (gTTS) synthesis + Radio-over-IP (RoIP) dispatch service.

Flow:
  1. Compose an urgent voice alert message.
  2. Synthesize it to a temporary .mp3 file using gTTS (natural AI voice).
  3. Put the file path onto the shared audio_queue for the Discord bot to play.

⚠️  gTTS performs a synchronous HTTP request to fetch the audio. To avoid blocking 
   the FastAPI event loop, synthesis is wrapped in asyncio.to_thread().

Architecture Note:
  The old architecture posted .mp3 bytes via HTTP to a separate aiohttp server on
  port 8001. The new architecture uses an in-process asyncio.Queue, eliminating
  the need for a second port/process. The Discord bot consumer picks up the file
  path and plays it in the voice channel, then deletes the temp file.
"""

import asyncio
import logging
import os
import tempfile
import uuid

import httpx

from app.config import settings
from app.core.audio_queue import audio_queue, DispatchPayload

logger = logging.getLogger(__name__)

# Fallback check for DISCORD_WEBHOOK_URL (Text notifications)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
if not DISCORD_WEBHOOK_URL:
    logger.warning("⚠️  DISCORD_WEBHOOK_URL is missing or empty. Text alerts will not be sent to Discord.")
else:
    logger.info("✅ DISCORD_WEBHOOK_URL loaded successfully.")


class TTSGenerationError(Exception):
    """Custom exception raised when TTS generation fails."""
    pass


def _synthesize_tts_file(message: str, output_path: str) -> None:
    """
    Synthesizes speech using the official Google Cloud Text-to-Speech API.
    Configured with 'en-IN' language and 'en-IN-Wavenet-C' voice for a natural 
    Indian English accent.
    """
    try:
        # Import inside the function to keep it localized, or at module level if preferred.
        # It's better to import at the top level for performance, but this is a background task.
        from google.cloud import texttospeech

        client = texttospeech.TextToSpeechClient()

        synthesis_input = texttospeech.SynthesisInput(text=message)

        voice = texttospeech.VoiceSelectionParams(
            language_code="en-IN",
            name="en-IN-Wavenet-C"
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        with open(output_path, "wb") as out:
            out.write(response.audio_content)
            
    except Exception as exc:
        logger.error("Google Cloud TTS API failed: %s", exc)
        raise TTSGenerationError(f"Failed to synthesize speech: {exc}") from exc


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
    3. Puts the file path onto the shared audio_queue for the Discord bot.
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

        print("[RoIP] OK TTS synthesis complete. Dispatching to queue ...", flush=True)
        logger.info("🔊  TTS synthesis complete. Dispatching to audio queue …")

        # Send text webhook if configured
        if DISCORD_WEBHOOK_URL:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(DISCORD_WEBHOOK_URL, json={"content": f"🚨 **RoIP Dispatch:** {message}"})
            except Exception as e:
                logger.error("Failed to send text webhook: %s", e)

        # ── Dispatch to Discord bot via in-process queue ──────────────────────
        # NOTE: The temp file is NOT deleted here — the Discord bot consumer
        # will delete it after playback is complete.
        await audio_queue.put(DispatchPayload(
            file_path=tmp_path,
            unit_code=police_unit_code,
            ambulance_id=ambulance_id,
            trigger_type=trigger_type,
        ))

        print(f"[RoIP] OK Queued for Discord playback: {tmp_path}", flush=True)
        logger.info(
            "✅  TTS audio queued for Discord playback | unit=%s | file=%s",
            police_unit_code,
            tmp_path,
        )

    except Exception as exc:
        print(f"[RoIP] ERROR Dispatch FAILED: {exc}", flush=True)
        logger.exception("❌  RoIP dispatch failed for ambulance %s: %s", ambulance_id, exc)
        # Clean up the temp file on synthesis/queue failure
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            print(f"[RoIP] DONE Temp file deleted on error: {tmp_path}", flush=True)
            logger.debug("🗑️   Temp audio file deleted: %s", tmp_path)