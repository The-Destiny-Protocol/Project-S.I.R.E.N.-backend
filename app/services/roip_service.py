"""
app/services/roip_service.py
────────────────────────────
Offline Text-to-Speech synthesis + Radio-over-IP (RoIP) dispatch service.

Flow:
  1. Compose an urgent voice alert message.
  2. Synthesize it to a temporary .wav file using pyttsx3 (fully offline, no cloud API).
  3. POST the .wav bytes to the configured RoIP gateway via httpx.AsyncClient.
  4. Clean up the temp file regardless of success or failure.

⚠️  pyttsx3 is a synchronous blocking library. To avoid freezing the FastAPI
    event loop, synthesis is always wrapped in asyncio.to_thread() when called
    from an async context.
"""

import asyncio
import logging
import os
import tempfile
import uuid

import httpx

logger = logging.getLogger(__name__)

# Target RoIP gateway — the Discord bot's aiohttp server (port 8001).
# Swap this for a real gateway URL in production.
ROIP_GATEWAY_URL = "http://localhost:8001/api/v1/emergency/mock-roip-gateway"


def _synthesize_tts_file(message: str, output_path: str) -> None:
    """
    Blocking pyttsx3 call — initializes a FRESH engine per call to avoid
    Windows COM/SAPI5 threading issues when pyttsx3 is reused across threads.

    Always call engine.stop() before returning so the COM object is fully
    released before the thread exits. Must be invoked via asyncio.to_thread().
    """
    import pyttsx3  # lazy import — only pull in the library when TTS is needed

    engine = pyttsx3.init()
    try:
        engine.setProperty("rate", 150)    # words per minute (slower = clearer)
        engine.setProperty("volume", 1.0)  # full volume
        engine.save_to_file(message, output_path)
        engine.runAndWait()
    finally:
        engine.stop()  # ← critical: releases Windows COM / SAPI5 resources


async def generate_and_dispatch_audio(
    police_unit_code: str,
    ambulance_id: str,
    trigger_type: str,
    radio_channel_id: str | None = None,
) -> None:
    """
    Async entry point used by BackgroundTasks in the SOS endpoint.

    1. Builds a clear, urgent radio-ready alert message.
    2. Synthesizes to a temp .wav via pyttsx3 (in a thread pool worker).
    3. POSTs the audio bytes to the RoIP gateway.
    4. Deletes the temp file.
    """
    # ── Visible diagnostics — print() is guaranteed to flush even before
    # logging handlers are fully configured (important for background threads).
    # NOTE: No emoji in print() — Windows cp1252 terminal cannot encode them.
    print(f"[RoIP] >> Background TTS task STARTED | unit={police_unit_code} ambulance={ambulance_id} trigger={trigger_type}", flush=True)
    logger.info(
        "🔊  [RoIP] Background TTS task started | unit=%s ambulance=%s trigger=%s",
        police_unit_code, ambulance_id, trigger_type,
    )

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
        f"Ambulance ID {ambulance_id} is blocked and requires immediate corridor clearance. "
        f"Please respond. Over."
    )

    tmp_path = os.path.join(tempfile.gettempdir(), f"roip_{uuid.uuid4().hex}.wav")
    print(f"[RoIP] Synthesizing speech -> {tmp_path}", flush=True)
    logger.info("🔊  Synthesizing TTS alert → %s", tmp_path)

    try:
        # Run blocking pyttsx3 synthesis in a thread pool to not block the event loop
        await asyncio.to_thread(_synthesize_tts_file, message, tmp_path)

        print("[RoIP] OK TTS synthesis complete. Dispatching to gateway ...", flush=True)
        logger.info("🔊  TTS synthesis complete. Dispatching to RoIP gateway …")

        # POST the .wav bytes to the gateway
        with open(tmp_path, "rb") as audio_file:
            audio_bytes = audio_file.read()

        print(f"[RoIP] Sending {len(audio_bytes)} bytes to {ROIP_GATEWAY_URL}", flush=True)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                ROIP_GATEWAY_URL,
                content=audio_bytes,
                headers={
                    "Content-Type": "audio/wav",
                    "X-Police-Unit": police_unit_code,
                    "X-Ambulance-Id": ambulance_id,
                    "X-Trigger-Type": trigger_type,
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


