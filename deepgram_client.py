"""
Deepgram Client Module
Handles connection to Deepgram's Speech-to-Text API
"""
import asyncio
import json
from typing import Callable
from deepgram import Deepgram
from config import Config

class DeepgramTranscriber:
    """Manages Deepgram transcription connection"""

    def __init__(self, on_transcript_callback: Callable[[str, bool], None]):
        """
        Initialize Deepgram transcriber

        Args:
            on_transcript_callback: Function to call when transcript is received
                                   Signature: callback(text: str, is_final: bool)
        """
        self.on_transcript_callback = on_transcript_callback
        self.connection = None
        self.is_connected = False

        # Initialize Deepgram client with the older SDK
        self.deepgram = Deepgram(Config.DEEPGRAM_API_KEY)

    async def connect(self) -> bool:
        """
        Establish connection to Deepgram

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Configure transcription options for older SDK
            options = {
                'punctuate': True,
                'interim_results': True,
                'language': 'en-US',
                'model': 'nova-2',
                'encoding': 'mulaw',
                'sample_rate': 8000,
                'channels': 1
            }

            # Create connection using older SDK
            self.connection = await self.deepgram.transcription.live(options)

            # Register event handlers - handlers receive only the message body
            def handle_close(msg):
                print(f"[Deepgram] Close event")
                self._on_close()

            def handle_transcript(msg):
                print(f"[Deepgram] Transcript event received")
                self._on_transcript(msg)

            def handle_error(msg):
                print(f"[Deepgram] Error event: {msg}")

            self.connection.registerHandler(
                self.connection.event.CLOSE,
                handle_close
            )

            self.connection.registerHandler(
                self.connection.event.TRANSCRIPT_RECEIVED,
                handle_transcript
            )

            self.connection.registerHandler(
                self.connection.event.ERROR,
                handle_error
            )

            self.is_connected = True
            print("[Deepgram] Connection established")
            return True

        except Exception as e:
            print(f"[Deepgram] Connection error: {e}")
            import traceback
            traceback.print_exc()
            self.is_connected = False
            return False


    async def send_audio(self, audio_data: bytes) -> None:
        """
        Send audio data to Deepgram

        Args:
            audio_data: Raw audio bytes (mulaw encoded)
        """
        if self.connection and self.is_connected:
            try:
                self.connection.send(audio_data)
            except Exception as e:
                print(f"[Deepgram] Error sending audio: {e}")

    async def close(self) -> None:
        """Close the Deepgram connection"""
        if self.connection:
            try:
                await self.connection.finish()
                self.is_connected = False
                print("[Deepgram] Connection closed")
            except Exception as e:
                print(f"[Deepgram] Error closing connection: {e}")

    def _on_transcript(self, message) -> None:
        """Called when transcript is received"""
        try:
            print(f"[Deepgram] Raw message received: {type(message)}")

            # Parse the message
            if isinstance(message, str):
                data = json.loads(message)
            else:
                data = message

            print(f"[Deepgram] Parsed data keys: {data.keys() if isinstance(data, dict) else 'not a dict'}")

            # Extract transcript from the response
            if 'channel' in data:
                alternatives = data['channel']['alternatives']
                if alternatives and len(alternatives) > 0:
                    transcript = alternatives[0]['transcript']

                    if len(transcript) > 0:
                        is_final = data.get('is_final', False)
                        print(f"[Deepgram] Calling callback with: is_final={is_final}, text='{transcript}'")
                        self.on_transcript_callback(transcript, is_final)
                    else:
                        print(f"[Deepgram] Empty transcript, skipping")
                else:
                    print(f"[Deepgram] No alternatives in response")
            else:
                print(f"[Deepgram] No 'channel' key in response")

        except Exception as e:
            print(f"[Deepgram] Error processing transcript: {e}")
            import traceback
            traceback.print_exc()

    def _on_close(self) -> None:
        """Called when connection closes"""
        print("[Deepgram] Connection closed by server")
        self.is_connected = False
