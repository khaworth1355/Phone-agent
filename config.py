"""
Configuration Module
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Twilio credentials
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

    # Deepgram API key
    DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')

    # Anthropic Claude API
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    # Using Claude 3 Haiku - fast and efficient for phone calls
    CLAUDE_MODEL = os.getenv('CLAUDE_MODEL', 'claude-3-haiku-20240307')

    # Claude system prompt (can be customized)
    CLAUDE_SYSTEM_PROMPT = os.getenv('CLAUDE_SYSTEM_PROMPT',
        'You are a helpful AI assistant answering phone calls. '
        'Keep your responses concise and natural for voice conversation. '
        'Speak clearly and avoid overly long responses.')

    # ElevenLabs TTS
    ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
    ELEVENLABS_VOICE_ID = os.getenv('ELEVENLABS_VOICE_ID', '21m00Tcm4TlvDq8ikWAM')  # Rachel
    ELEVENLABS_MODEL = os.getenv('ELEVENLABS_MODEL', 'eleven_turbo_v2_5')

    # Cloudflare tunnel URL (update this with your current tunnel)
    # Format: wss://your-tunnel.trycloudflare.com/media
    WEBSOCKET_URL = os.getenv('WEBSOCKET_URL', 'wss://administration-robot-herbal-knight.trycloudflare.com/media')

    # Conversation settings
    PAUSE_THRESHOLD = float(os.getenv('PAUSE_THRESHOLD', '1.0'))  # Seconds of silence before triggering response
    RESPONSE_TIMEOUT = float(os.getenv('RESPONSE_TIMEOUT', '15.0'))  # Max time for Claude/ElevenLabs

    # Flask settings
    PORT = 5000
    DEBUG = True
