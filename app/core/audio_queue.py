"""
app/core/audio_queue.py
───────────────────────
Shared asyncio.Queue for in-process RoIP audio dispatch.

Instead of HTTP-posting audio bytes to a separate aiohttp server on port 8001,
the RoIP service now puts a DispatchPayload onto this queue. The Discord bot's
queue consumer task picks it up and plays the audio in the voice channel.

This eliminates the need for a second process/port and enables single-port
deployment on platforms like Render.
"""

import asyncio
from dataclasses import dataclass


@dataclass
class DispatchPayload:
    """Data object passed through the audio queue from roip_service → discord bot."""
    file_path: str
    unit_code: str
    ambulance_id: str
    trigger_type: str


# ── Singleton Queue ───────────────────────────────────────────────────────────
# Shared across the entire FastAPI process. Producers (roip_service) put items,
# the Discord bot consumer gets items.
audio_queue: asyncio.Queue[DispatchPayload] = asyncio.Queue()
