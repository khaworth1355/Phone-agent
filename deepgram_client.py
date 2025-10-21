"""
Deepgram Client Module
Handles connection to Deepgram's Speech-to-Text API
"""
import asyncio
import json
from typing import Callable, Optional
from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents, LiveOptions
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

        # Initialize Deepgram client
        config = DeepgramClientOptions(
            options={"keepalive": "true"}
        )
        self.deepgram = DeepgramClient(Config.DEEPGRAM_API_KEY, config)

    async def connect(self) -> bool:
        """
        Establish connection to Deepgram

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Configure transcription options
            options = LiveOptions(
                model="nova-2",
                language="en-US",
                smart_format=True,
                encoding="mulaw",
                sample_rate=8000,
                channels=1,
                interim_results=True,
                utterance_end_ms=1000,
                vad_events=True,
            )

            # Create connection
            self.connection = self.deepgram.listen.asynclive.v("1")

            # Set up event handlers
            self.connection.on(LiveTranscriptionEvents.Open, self._on_open)
            self.connection.on(LiveTranscriptionEvents.Transcript, self._on_transcript)
            self.connection.on(LiveTranscriptionEvents.Error, self._on_error)
            self.connection.on(LiveTranscriptionEvents.Close, self._on_close)

            # Start the connection
            await self.connection.start(options)

            self.is_connected = True
            print("[Deepgram] Connection established")
            return True

        except Exception as e:
            print(f"[Deepgram] Connection error: {e}")
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
                await self.connection.send(audio_data)
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

    def _on_open(self, *args, **kwargs) -> None:
        """Called when connection opens"""
        print("[Deepgram] Connection opened successfully")

    def _on_transcript(self, *args, **kwargs) -> None:
        """Called when transcript is received"""
        result = kwargs.get('result')
        if not result:
            return

        # Extract transcript
        transcript = result.channel.alternatives[0].transcript

        if len(transcript) > 0:
            is_final = result.is_final
            self.on_transcript_callback(transcript, is_final)

    def _on_error(self, error, **kwargs) -> None:
        """Called when an error occurs"""
        print(f"[Deepgram] Error: {error}")

    def _on_close(self, *args, **kwargs) -> None:
        """Called when connection closes"""
        print("[Deepgram] Connection closed")
        self.is_connected = False
