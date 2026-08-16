"""
app/services/roip_service.py
────────────────────────────
Offline Piper Text-to-Speech (TTS) synthesis + Radio-over-IP (RoIP) dispatch service.

Flow:
  1. Compose an urgent voice alert message.
  2. Synthesize it to a temporary .mp3 file using Amazon Polly.
  3. Put the file path onto the shared audio_queue for the Discord bot to play.

⚠️  Amazon Polly audio conversion performs a synchronous HTTP request. To avoid blocking 
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
import subprocess
import wave

import httpx

from app.config import settings
from app.core.audio_queue import audio_queue, DispatchPayload
import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

# Fallback check for DISCORD_WEBHOOK_URL (Text notifications)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
if not DISCORD_WEBHOOK_URL:
    logger.warning("⚠️  DISCORD_WEBHOOK_URL is missing or empty. Text alerts will not be sent to Discord.")
else:
    logger.info("✅ DISCORD_WEBHOOK_URL loaded successfully.")


class TTSGenerationError(Exception):
    """Custom exception raised when offline TTS or audio conversion fails."""
    pass

# Initialize Amazon Polly client globally
try:
    polly_client = boto3.client(
        'polly',
        aws_access_key_id=settings.aws_access_key_id if settings.aws_access_key_id else None,
        aws_secret_access_key=settings.aws_secret_access_key if settings.aws_secret_access_key else None,
        region_name=settings.aws_default_region
    )
except Exception as e:
    logger.warning("⚠️ Failed to initialize Amazon Polly client. TTS will fail. Error: %s", e)
    polly_client = None


def _synthesize_tts_file(message: str, output_path: str) -> None:
    """
    Synthesizes speech using Amazon Polly.
    Writes the resulting .mp3 audio stream directly to the file.
    """
    if not polly_client:
        raise TTSGenerationError("Amazon Polly client is not loaded.")
            
    try:
        response = polly_client.synthesize_speech(
            Text=message,
            OutputFormat='mp3',
            VoiceId='Aditi',
            Engine='standard'
        )
        
        if "AudioStream" in response:
            with open(output_path, "wb") as file:
                file.write(response["AudioStream"].read())
        else:
            raise TTSGenerationError("No AudioStream returned from Amazon Polly.")
            
    except (BotoCoreError, ClientError) as error:
        raise TTSGenerationError(f"AWS Polly synthesis failed: {error}")
    except Exception as e:
        raise TTSGenerationError(f"TTS Synthesis failed: {e}")


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
    2. Synthesizes to a temp .mp3 via Amazon Polly (in a thread pool worker).
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
        # Run blocking TTS synthesis in a thread pool to avoid blocking the event loop
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