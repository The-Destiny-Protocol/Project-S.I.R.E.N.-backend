import asyncio
import os
import tempfile
import uuid
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

from app.services.roip_service import _synthesize_tts_file
from app.core.audio_queue import audio_queue, DispatchPayload
from discord_gateway.discord_bot import start_discord_bot, stop_discord_bot

async def main():
    print("Starting bot...")
    bot_task = asyncio.create_task(start_discord_bot())
    
    print("Waiting 5 seconds for bot to login...")
    await asyncio.sleep(5)
    
    tmp = os.path.join(tempfile.gettempdir(), f'test_{uuid.uuid4().hex}.mp3')
    print(f"Synthesizing to {tmp}...")
    _synthesize_tts_file('Testing the Discord Bot integration. The system is online.', tmp)
    
    print("Putting payload in queue...")
    await audio_queue.put(DispatchPayload(
        file_path=tmp, 
        unit_code='TEST-UNIT', 
        ambulance_id='AMB-123', 
        trigger_type='MANUAL_DRIVER_SOS'
    ))
    
    print("Waiting 12 seconds for bot to play audio...")
    await asyncio.sleep(12)
    
    print("Stopping bot...")
    await stop_discord_bot()
    bot_task.cancel()
    print("TEST COMPLETE")

if __name__ == "__main__":
    asyncio.run(main())
