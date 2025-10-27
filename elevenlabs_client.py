"""
ElevenLabs TTS Client - Text-to-Speech for phone calls
"""
import asyncio
import io
import base64
from typing import Optional
from config import Config

try:
    import requests
    DEPENDENCIES_AVAILABLE = True
    try:
        from pydub import AudioSegment
    except ImportError as e:
        # pydub might fail on Python 3.14 due to missing audioop
        print(f"[ElevenLabs] Warning: pydub import issue: {e}")
        DEPENDENCIES_AVAILABLE = False
except ImportError:
    DEPENDENCIES_AVAILABLE = False
    print("[ElevenLabs] Warning: Missing dependencies (requests, pydub)")


class ElevenLabsClient:
    """Handles text-to-speech conversion using ElevenLabs"""

    def __init__(self):
        """Initialize ElevenLabs client"""
        self.api_key = Config.ELEVENLABS_API_KEY
        self.voice_id = Config.ELEVENLABS_VOICE_ID
        self.model = Config.ELEVENLABS_MODEL
        self.base_url = "https://api.elevenlabs.io/v1"

        print(f"[ElevenLabs] Client initialized")
        print(f"[ElevenLabs] Voice ID: {self.voice_id}")
        print(f"[ElevenLabs] Model: {self.model}")

        if not DEPENDENCIES_AVAILABLE:
            print("[ElevenLabs] ⚠️ Missing dependencies! Install: pip install requests pydub")

    async def text_to_speech(self, text: str, timeout: Optional[float] = None) -> Optional[bytes]:
        """
        Convert text to speech audio suitable for Twilio

        Args:
            text: Text to convert to speech
            timeout: Timeout in seconds (uses Config.RESPONSE_TIMEOUT if None)

        Returns:
            Audio bytes in mulaw format, 8kHz, mono (Twilio compatible)
            Returns None on error
        """
        if not DEPENDENCIES_AVAILABLE:
            print("[ElevenLabs] ❌ Cannot generate speech - missing dependencies")
            return None

        if not self.api_key or self.api_key == "your_elevenlabs_api_key_here":
            print("[ElevenLabs] ❌ No API key configured")
            return None

        timeout = timeout or Config.RESPONSE_TIMEOUT

        try:
            print(f"[ElevenLabs] Generating speech for: '{text}' (timeout: {timeout}s)")

            # Call ElevenLabs API
            audio_data = await asyncio.wait_for(
                self._generate_speech(text),
                timeout=timeout
            )

            if not audio_data:
                return None

            # Convert to Twilio format (mulaw, 8kHz, mono)
            converted_audio = await self._convert_to_twilio_format(audio_data)

            if converted_audio:
                print(f"[ElevenLabs] ✅ Generated {len(converted_audio)} bytes of audio")

            return converted_audio

        except asyncio.TimeoutError:
            print(f"[ElevenLabs] ⏱️ Timeout after {timeout}s")
            return None

        except Exception as e:
            print(f"[ElevenLabs] ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def _generate_speech(self, text: str) -> Optional[bytes]:
        """
        Call ElevenLabs API to generate speech

        Args:
            text: Text to convert

        Returns:
            Raw audio bytes from ElevenLabs (MP3 format)
        """
        url = f"{self.base_url}/text-to-speech/{self.voice_id}"

        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }

        data = {
            "text": text,
            "model_id": self.model,
            "voice_settings": {
                "stability": 0.2,
                "similarity_boost": 0.99,
                "style": 0.8,
                "use_speaker_boost": True
            }
        }

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(url, json=data, headers=headers)
        )

        if response.status_code == 200:
            return response.content
        else:
            print(f"[ElevenLabs] API error: {response.status_code} - {response.text}")
            return None

    async def _convert_to_twilio_format(self, audio_data: bytes) -> Optional[bytes]:
        """
        Convert audio to Twilio-compatible format

        Twilio expects:
        - Encoding: mulaw (G.711 μ-law)
        - Sample rate: 8000 Hz
        - Channels: 1 (mono)

        Args:
            audio_data: Input audio bytes (MP3 from ElevenLabs)

        Returns:
            Converted audio bytes in raw mulaw format (compatible with Twilio)
        """
        try:
            # Load audio (ElevenLabs returns MP3)
            audio = AudioSegment.from_mp3(io.BytesIO(audio_data))

            # Convert to Twilio format: 8kHz, mono
            audio = audio.set_frame_rate(8000)  # 8kHz sample rate
            audio = audio.set_channels(1)  # Mono

            # Export as raw mulaw using ffmpeg
            # Use 'mulaw' format which outputs raw G.711 μ-law without container
            raw_buffer = io.BytesIO()
            audio.export(
                raw_buffer,
                format="mulaw",
                parameters=["-ar", "8000", "-ac", "1"]
            )

            raw_buffer.seek(0)
            mulaw_data = raw_buffer.read()

            print(f"[ElevenLabs] Converted to mulaw: {len(mulaw_data)} bytes")
            return mulaw_data

        except Exception as e:
            print(f"[ElevenLabs] ❌ Audio conversion error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_fallback_audio(self) -> Optional[bytes]:
        """
        Generate a simple fallback audio message

        Returns:
            Mulaw audio bytes for "I'm sorry, there was an error"
        """
        # For now, return None - we'll handle this with text fallback
        # In production, you might want to pre-generate this
        return None
