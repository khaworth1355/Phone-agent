"""
Configuration Module
"""
import os
from dotenv import load_dotenv

load_dotenv()


def load_knowledge_base():
    """Load knowledge base from file if it exists"""
    kb_path = os.path.join(os.path.dirname(__file__), 'knowledge_base.txt')
    try:
        if os.path.exists(kb_path):
            with open(kb_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    print(f"[Config] Loaded knowledge base ({len(content)} chars)")
                    return content
        print(f"[Config] No knowledge base found at {kb_path}")
        return ""
    except Exception as e:
        print(f"[Config] Error loading knowledge base: {e}")
        return ""


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

    # Claude system prompt (can be customized via environment or knowledge_base.txt)
    _base_prompt = os.getenv('CLAUDE_SYSTEM_PROMPT',
        'You are a helpful AI assistant answering phone calls for TEMCO.\n\n'
        '⚡ RESPONSE SPEED & LENGTH REQUIREMENTS - CRITICAL:\n'
        '- Respond INSTANTLY - caller is waiting on the line\n'
        '- Keep ALL responses to 1-2 sentences maximum (3 sentences ONLY if absolutely necessary)\n'
        '- Be direct and to the point - no filler words, no pleasantries\n'
        '- Answer the specific question asked, nothing more\n'
        '- For simple questions (price, location), give 1 sentence answers\n'
        '- Do NOT overthink - give the first clear answer that comes to mind\n'
        '- Speak naturally but briefly - this is a phone call, not an essay\n'
        '- Example good response: "The T5 costs $10,000 and has a 30 inch turntable."\n'
        '- Example bad response: Long paragraphs with multiple features listed\n\n'
        '🔴 CRITICAL CALL TRANSFER CAPABILITY - YOU CAN TRANSFER CALLS:\n'
        'You have the ability to transfer calls to the sales team. DO NOT tell callers you cannot transfer them.\n'
        'When a caller says ANY of these phrases:\n'
        '- "I want to buy" / "I want to purchase" / "I\'d like to buy"\n'
        '- "Transfer me to sales" / "Connect me to sales" / "Speak to sales"\n'
        '- "Place an order" / "Make a purchase"\n'
        '- Any purchasing or buying intent\n\n'
        'YOU MUST:\n'
        '1. Acknowledge their request positively (e.g., "I\'d be happy to connect you with our sales team")\n'
        '2. Add [TRANSFER_TO_SALES] at the END of your response\n'
        '3. DO NOT say you cannot transfer - you CAN and WILL transfer them\n\n'
        'Example response: "I\'d be happy to connect you with our sales team to complete your purchase. [TRANSFER_TO_SALES]"\n'
        'The marker MUST be exactly [TRANSFER_TO_SALES] in square brackets.')

    # Load knowledge base and append to system prompt
    _knowledge_base = load_knowledge_base()
    if _knowledge_base:
        CLAUDE_SYSTEM_PROMPT = f"{_base_prompt}\n\n" \
                               f"=== COMPANY KNOWLEDGE BASE ===\n" \
                               f"Use this information to answer questions accurately:\n\n" \
                               f"{_knowledge_base}"
    else:
        CLAUDE_SYSTEM_PROMPT = _base_prompt

    # ElevenLabs TTS
    ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
    ELEVENLABS_VOICE_ID = os.getenv('ELEVENLABS_VOICE_ID', '21m00Tcm4TlvDq8ikWAM')  # Rachel
    ELEVENLABS_MODEL = os.getenv('ELEVENLABS_MODEL', 'eleven_turbo_v2_5')

    # WebSocket URL for Twilio media stream
    # Production: Set this to wss://YOUR_DROPLET_IP/media or wss://your-domain.com/media
    # Development: Use Cloudflare tunnel or ngrok
    WEBSOCKET_URL = os.getenv('WEBSOCKET_URL', 'wss://localhost/media')

    # Base URL for webhooks (HTTP/HTTPS version of WEBSOCKET_URL domain)
    # Production: https://your-domain.com or https://YOUR_DROPLET_IP
    BASE_URL = os.getenv('BASE_URL', 'https://localhost')

    # Conversation settings
    PAUSE_THRESHOLD = float(os.getenv('PAUSE_THRESHOLD', '0.3'))  # Seconds of silence before triggering response
    RESPONSE_TIMEOUT = float(os.getenv('RESPONSE_TIMEOUT', '15.0'))  # Max time for Claude/ElevenLabs

    # Predictive response settings
    PREDICTIVE_RESPONSES = bool(os.getenv('PREDICTIVE_RESPONSES', 'True'))  # Start generating on interim transcripts
    INTERIM_STABILITY_THRESHOLD = int(os.getenv('INTERIM_STABILITY_THRESHOLD', '3'))  # Number of matching interims to trigger

    # Call forwarding
    SALES_FORWARD_NUMBER = os.getenv('SALES_FORWARD_NUMBER', '+18166741783')  # Sales team number

    # Database
    DATABASE_URL = os.getenv('DATABASE_URL')

    # Admin interface settings
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'changeme123')  # Change this in production!
    ADMIN_ENABLED = os.getenv('ADMIN_ENABLED', 'true').lower() == 'true'

    # Flask settings
    PORT = int(os.getenv('PORT', 5000))
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
