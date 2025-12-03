"""
Deepgram Client - Simple wrapper for speech-to-text
"""
import asyncio
import json
from deepgram import Deepgram
from config import Config


class DeepgramClient:
    """Handles Deepgram connection and transcription"""

    def __init__(self, callback):
        """
        Initialize Deepgram client

        Args:
            callback: Function to call with (text, is_final) when transcript received
        """
        self.callback = callback
        self.deepgram = Deepgram(Config.DEEPGRAM_API_KEY)
        self.connection = None
        self.connected = False
        self.audio_sent_count = 0
        self.total_bytes_sent = 0

    async def connect(self):
        """Connect to Deepgram with enhanced accuracy settings"""
        try:
            print("[Deepgram] Connecting with enhanced model...")

            options = {
                'punctuate': True,
                'interim_results': True,
                'language': 'en-US',
                'model': 'nova-2-phonecall',  # UPGRADED: Optimized for phone calls
                'encoding': 'mulaw',
                'sample_rate': 8000,
                'channels': 1,
                'smart_format': True,  # NEW: Better formatting of numbers, dates, times
                'filler_words': True,  # NEW: Detect um, uh, etc.
                'profanity_filter': False,  # Keep actual words spoken
                # Custom vocabulary for domain-specific terms
                'keywords': [
                    'TEMCO', 'sales', 'support', 'billing'
                ],
                'keywords_boost': 2.0  # Prefer these words when ambiguous
            }

            self.connection = await self.deepgram.transcription.live(options)

            # Register handlers
            self.connection.registerHandler(
                self.connection.event.TRANSCRIPT_RECEIVED,
                self._on_message
            )

            self.connection.registerHandler(
                self.connection.event.ERROR,
                self._on_error
            )

            self.connected = True
            print("[Deepgram] ✓ Connected")
            return True

        except Exception as e:
            print(f"[Deepgram] ✗ Connection failed: {e}")
            return False

    async def send(self, audio_bytes):
        """Send audio to Deepgram"""
        if self.connection and self.connected:
            try:
                self.connection.send(audio_bytes)
                self.audio_sent_count += 1
                self.total_bytes_sent += len(audio_bytes)

                # Log first few sends
                if self.audio_sent_count <= 3:
                    print(f"[Deepgram] Sent audio chunk #{self.audio_sent_count}, size: {len(audio_bytes)} bytes")
                elif self.audio_sent_count == 50:
                    print(f"[Deepgram] Sent 50 chunks, total: {self.total_bytes_sent} bytes")

                # Send keepalive every 5 seconds (250 chunks at 20ms each)
                if self.audio_sent_count % 250 == 0:
                    self.connection.send(json.dumps({"type": "KeepAlive"}))
                    print(f"[Deepgram] Sent KeepAlive at chunk {self.audio_sent_count}")

            except Exception as e:
                print(f"[Deepgram] Error sending audio: {e}")
        else:
            print(f"[Deepgram] Cannot send - connected: {self.connected}, connection: {self.connection is not None}")

    async def close(self):
        """Close connection"""
        if self.connection:
            await self.connection.finish()
            self.connected = False
            print(f"[Deepgram] Connection closed - Sent {self.audio_sent_count} chunks, {self.total_bytes_sent} total bytes")

    def _on_message(self, message):
        """Handle transcript messages"""
        # PERFORMANCE FIX: Removed verbose logging that blocks event loop on server
        # print(f"[Deepgram] Message received: {message}")
        try:
            # Parse message
            data = json.loads(message) if isinstance(message, str) else message

            # Extract transcript
            if 'channel' in data:
                alternatives = data['channel']['alternatives']
                if alternatives and len(alternatives) > 0:
                    transcript = alternatives[0]['transcript']
                    if transcript:
                        is_final = data.get('is_final', False)
                        self.callback(transcript, is_final)

        except Exception as e:
            print(f"[Deepgram] Error processing message: {e}")

    def _on_error(self, error):
        """Handle errors"""
        print(f"[Deepgram] Error: {error}")
