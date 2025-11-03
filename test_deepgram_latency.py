"""
Test Deepgram latency from server
"""
import time
import asyncio
from deepgram import Deepgram
from config import Config

async def test_latency():
    dg = Deepgram(Config.DEEPGRAM_API_KEY)

    # Create a simple audio buffer (1 second of silence)
    silence = b'\xff' * 8000  # mulaw silence

    options = {
        'punctuate': False,
        'interim_results': False,
        'language': 'en-US',
        'model': 'nova-2',
        'encoding': 'mulaw',
        'sample_rate': 8000,
        'channels': 1
    }

    print("Testing Deepgram connection latency...")
    start = time.time()
    conn = await dg.transcription.live(options)
    connect_time = time.time() - start

    print(f'✓ Connection time: {connect_time:.2f}s')

    print("Sending audio and waiting for response...")
    send_start = time.time()
    conn.send(silence)
    await asyncio.sleep(2)  # Wait for response
    await conn.finish()
    total_time = time.time() - send_start

    print(f'✓ Total round-trip time: {total_time:.2f}s')

    if connect_time > 1.0:
        print(f"\n⚠️  WARNING: Connection time is high ({connect_time:.2f}s)")
        print("This suggests network latency to Deepgram servers.")

    if total_time > 3.0:
        print(f"\n⚠️  WARNING: Round-trip time is high ({total_time:.2f}s)")
        print("This will cause significant delays in your phone agent.")

if __name__ == "__main__":
    asyncio.run(test_latency())
