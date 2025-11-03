"""
Test Deepgram real-time streaming latency (simulates actual phone agent workflow)

This test:
1. Records when we start streaming
2. Sends keepalive packets to keep connection alive
3. Measures empty result delays to identify buffering
4. Compares to your production logs

Run this on your server to confirm if the delay is Deepgram-specific.
"""
import asyncio
import time
import json
from deepgram import Deepgram
from config import Config

class StreamingLatencyTest:
    def __init__(self):
        self.stream_start_time = None
        self.first_empty_result_time = None
        self.empty_results_count = 0
        self.messages_received = []

    async def run_test(self):
        """Run the streaming latency test"""
        print("="*80)
        print("DEEPGRAM STREAMING LATENCY TEST")
        print("="*80)
        print("This test measures Deepgram's response timing for streaming audio.")
        print("We'll stream silence and measure when Deepgram sends back results.")
        print("="*80)
        print()

        # Connect to Deepgram
        dg = Deepgram(Config.DEEPGRAM_API_KEY)

        options = {
            'punctuate': True,
            'interim_results': True,
            'language': 'en-US',
            'model': 'nova-2',
            'encoding': 'mulaw',
            'sample_rate': 8000,
            'channels': 1
        }

        print("Connecting to Deepgram...")
        connect_start = time.time()
        connection = await dg.transcription.live(options)
        connect_time = time.time() - connect_start
        print(f"✓ Connected in {connect_time:.3f}s")
        print()

        # Register message handler
        def on_message(msg):
            msg_time = time.time()
            elapsed = msg_time - self.stream_start_time

            try:
                data = json.loads(msg) if isinstance(msg, str) else msg

                if 'channel' in data:
                    duration = data.get('duration', 0)
                    is_final = data.get('is_final', False)

                    if self.first_empty_result_time is None:
                        self.first_empty_result_time = elapsed
                        print(f"  [{elapsed:6.2f}s] First result received (duration: {duration:.2f}s)")

                    self.empty_results_count += 1
                    self.messages_received.append({
                        'time': elapsed,
                        'duration': duration,
                        'is_final': is_final
                    })

                    # Log every 5th message to show progress
                    if self.empty_results_count % 5 == 0:
                        status = "final" if is_final else "interim"
                        print(f"  [{elapsed:6.2f}s] Result #{self.empty_results_count} ({status}, duration: {duration:.2f}s)")

            except Exception as e:
                print(f"  Error processing message: {e}")

        connection.registerHandler(connection.event.TRANSCRIPT_RECEIVED, on_message)

        # Stream silence in 160-byte chunks (20ms each) for 15 seconds
        print("Streaming silence for 15 seconds (160 bytes every 20ms)...")
        print("Measuring when Deepgram sends back empty results...")
        print()

        silence_byte = b'\xff'  # mulaw silence
        chunk = silence_byte * 160  # 20ms chunk

        self.stream_start_time = time.time()
        chunks_sent = 0

        # Stream for 15 seconds
        for i in range(750):  # 750 chunks = 15 seconds
            connection.send(chunk)
            chunks_sent += 1

            # Log progress every 1 second (50 chunks)
            if i % 50 == 0:
                elapsed = time.time() - self.stream_start_time
                print(f"  [{elapsed:6.2f}s] Sent {chunks_sent} chunks")

            # Send keepalive every 5 seconds (250 chunks)
            if i % 250 == 0 and i > 0:
                connection.send(json.dumps({"type": "KeepAlive"}))
                print(f"  [{time.time() - self.stream_start_time:6.2f}s] Sent KeepAlive")

            # Wait 20ms before next chunk
            await asyncio.sleep(0.02)

        print()
        print("All audio sent. Waiting 3 seconds for final messages...")
        await asyncio.sleep(3)

        # Close connection
        await connection.finish()

        # Print results
        print()
        print("="*80)
        print("TEST RESULTS")
        print("="*80)
        print()

        print(f"Stream duration:             15.00s")
        print(f"Chunks sent:                 {chunks_sent}")
        print(f"Chunk size:                  160 bytes (20ms)")
        print()

        if self.first_empty_result_time:
            print(f"First result arrived at:     {self.first_empty_result_time:.2f}s")
            print(f"Total results received:      {self.empty_results_count}")
            print()

            # Compare to your production logs
            print("COMPARISON TO YOUR PRODUCTION LOGS:")
            print("-" * 80)
            print()
            print("Your production logs showed:")
            print("  - Stream starts at X")
            print("  - First result at X+10s (for audio at 0.5s)")
            print("  - Delay: ~9-10 seconds")
            print()
            print(f"This test shows:")
            print(f"  - Stream starts at 0s")
            print(f"  - First result at {self.first_empty_result_time:.2f}s")
            print(f"  - Delay: {self.first_empty_result_time:.2f}s")
            print()

            if self.first_empty_result_time > 5.0:
                print("❌ VERY SLOW: This matches your production delays!")
                print()
                print("   The ~10 second delay is confirmed to be from Deepgram.")
                print("   This is NOT normal behavior.")
                print()
                print("   POSSIBLE CAUSES:")
                print("   1. Network routing from DigitalOcean SF to Deepgram servers")
                print("   2. TCP buffering/windowing issues")
                print("   3. Regional server selection by Deepgram")
                print()
                print("   RECOMMENDED ACTIONS:")
                print("   1. Try DigitalOcean NYC region instead of SF")
                print("   2. Contact Deepgram support with these test results")
                print("   3. Try upgrading to Deepgram SDK 3.x")
            elif self.first_empty_result_time > 2.0:
                print("⚠️  SLOW: Moderate delay detected")
                print(f"   Expected: <1s, Got: {self.first_empty_result_time:.2f}s")
            else:
                print("✅ GOOD: Results arriving quickly")
                print("   This suggests the production delays are from something else")
        else:
            print("❌ No results received!")
            print("   This indicates a connection or API issue")

        print()
        print("="*80)

async def main():
    test = StreamingLatencyTest()
    await test.run_test()

if __name__ == "__main__":
    asyncio.run(main())
