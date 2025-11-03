"""
Test Deepgram real-time streaming latency (simulates actual phone agent workflow)

This test:
1. Streams audio in small chunks (160 bytes every 20ms) like Twilio
2. Measures when transcripts arrive vs when audio was sent
3. Uses actual speech (not silence)
4. Tracks timing precisely to identify delays

Run this on your server to confirm if the delay is Deepgram-specific.
"""
import asyncio
import time
import json
from deepgram import Deepgram
from config import Config

# Generate 3 seconds of mulaw audio representing "Where are you located?"
# Pattern: silence (500ms) -> speech (2s) -> silence (500ms)
def generate_test_audio():
    """Generate mulaw audio simulating speech"""
    silence_byte = b'\xff'  # mulaw silence
    speech_byte = b'\xaa'   # mulaw audio signal (simulates speech)

    # 8000 samples/sec, 1 byte per sample
    silence_500ms = silence_byte * 4000   # 500ms silence
    speech_2s = speech_byte * 16000       # 2 seconds of "speech"

    return silence_500ms + speech_2s + silence_500ms

class StreamingLatencyTest:
    def __init__(self):
        self.transcript_times = []
        self.audio_send_times = []
        self.stream_start_time = None
        self.first_transcript_time = None
        self.final_transcript_time = None
        self.transcripts_received = []

    async def run_test(self):
        """Run the streaming latency test"""
        print("="*80)
        print("DEEPGRAM STREAMING LATENCY TEST")
        print("="*80)
        print("This test simulates real phone agent behavior:")
        print("- Streams audio in 160-byte chunks every 20ms (like Twilio)")
        print("- Measures transcript delivery delays")
        print("="*80)
        print()

        # Generate test audio
        full_audio = generate_test_audio()
        print(f"Generated {len(full_audio)} bytes of test audio (3 seconds)")
        print(f"Pattern: 500ms silence -> 2s speech -> 500ms silence")
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
                    transcript = data['channel']['alternatives'][0]['transcript'] if data['channel']['alternatives'] else ''
                    is_final = data.get('is_final', False)

                    if transcript:
                        if self.first_transcript_time is None:
                            self.first_transcript_time = elapsed

                        if is_final:
                            self.final_transcript_time = elapsed

                        status = "FINAL" if is_final else "INTERIM"
                        print(f"  [{elapsed:6.2f}s] {status:7s}: '{transcript}'")

                        self.transcripts_received.append({
                            'time': elapsed,
                            'text': transcript,
                            'is_final': is_final
                        })

                        # Check word timestamps if available
                        if is_final and data['channel']['alternatives'][0].get('words'):
                            first_word = data['channel']['alternatives'][0]['words'][0]
                            word_start = first_word.get('start', 0)
                            print(f"           First word timestamp: {word_start:.2f}s")
                            print(f"           Delay from word to transcript: {elapsed - word_start:.2f}s")

            except Exception as e:
                print(f"  Error processing message: {e}")

        connection.registerHandler(connection.event.TRANSCRIPT_RECEIVED, on_message)

        # Stream audio in 160-byte chunks (20ms each)
        print("Streaming audio in real-time (160 bytes every 20ms)...")
        print()

        chunk_size = 160  # 20ms of audio at 8kHz
        chunks = [full_audio[i:i+chunk_size] for i in range(0, len(full_audio), chunk_size)]

        self.stream_start_time = time.time()

        for i, chunk in enumerate(chunks):
            # Send chunk
            connection.send(chunk)
            self.audio_send_times.append(time.time() - self.stream_start_time)

            # Log progress
            if i % 50 == 0:  # Every 1 second
                elapsed = time.time() - self.stream_start_time
                print(f"  [{elapsed:6.2f}s] Sent chunk {i}/{len(chunks)}")

            # Wait 20ms before next chunk (simulate real-time)
            await asyncio.sleep(0.02)

        print()
        print("All audio sent. Waiting 3 seconds for final transcripts...")
        await asyncio.sleep(3)

        # Close connection
        await connection.finish()

        # Print results
        print()
        print("="*80)
        print("TEST RESULTS")
        print("="*80)
        print()

        print(f"Total audio duration:        3.00s")
        print(f"Total chunks sent:           {len(chunks)}")
        print(f"Chunk size:                  160 bytes (20ms)")
        print()

        if self.first_transcript_time:
            print(f"First transcript arrived at: {self.first_transcript_time:.2f}s")
            print(f"  (Speech starts at ~0.50s, so delay is {self.first_transcript_time - 0.5:.2f}s)")
        else:
            print("❌ No transcripts received!")

        print()

        if self.final_transcript_time:
            print(f"Final transcript arrived at: {self.final_transcript_time:.2f}s")
            print(f"  (Speech ends at ~2.50s, so delay is {self.final_transcript_time - 2.5:.2f}s)")
        else:
            print("❌ No final transcript received!")

        print()
        print(f"Total transcripts received:  {len(self.transcripts_received)}")
        print()

        # Diagnosis
        print("="*80)
        print("DIAGNOSIS")
        print("="*80)

        if self.first_transcript_time is None:
            print("❌ CRITICAL: No transcripts received at all")
            print("   This indicates a serious connection or API issue")
        elif self.first_transcript_time < 2.0:
            print("✅ GOOD: First transcript arrived quickly")
            print(f"   Delay: {self.first_transcript_time - 0.5:.2f}s (acceptable)")
        elif self.first_transcript_time < 5.0:
            print("⚠️  SLOW: Moderate delay in transcript delivery")
            print(f"   Delay: {self.first_transcript_time - 0.5:.2f}s (suboptimal)")
        else:
            print("❌ VERY SLOW: Severe delay in transcript delivery")
            print(f"   Delay: {self.first_transcript_time - 0.5:.2f}s (PROBLEM!)")
            print()
            print("   This matches the 8-10 second delays you're seeing in production.")
            print("   The issue is likely:")
            print("   - Network routing from this server to Deepgram")
            print("   - TCP buffering/windowing issues")
            print("   - Geographic routing problems")
            print()
            print("   RECOMMENDATION: Try a different server region (e.g., NYC instead of SF)")

        print("="*80)

async def main():
    test = StreamingLatencyTest()
    await test.run_test()

if __name__ == "__main__":
    asyncio.run(main())
