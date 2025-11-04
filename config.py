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
        '🚨 CRITICAL PRIORITY #1 - DETERGENT ORDERS:\n'
        'If caller mentions ANY of these phrases, IMMEDIATELY start collecting information:\n'
        '- "order detergent" / "buy detergent" / "purchase detergent" / "want to order more detergent"\n'
        '- "order TurboKlean" / "buy TurboKlean"\n'
        '- "need more detergent" / "want more detergent" / "order more detergent"\n'
        'DO NOT give them phone numbers or tell them to call back. Start collecting info NOW.\n'
        'Your FIRST response MUST be: "I can help with that. May I have your name please?" [COLLECT_DETERGENT_NAME]\n\n'
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
        'The marker MUST be exactly [TRANSFER_TO_SALES] in square brackets.\n\n'
        '🧴 DETERGENT ORDER SPECIAL HANDLING:\n'
        'When a caller wants to buy/order MORE DETERGENT (TurboKlean), follow this EXACT process:\n\n'
        '1. COLLECT NAME: "I can help with that. May I have your name please?"\n'
        '   - Add [COLLECT_DETERGENT_NAME] at the END of your response\n\n'
        '2. COLLECT PHONE: After they provide name, ask: "Thank you [name]. What\'s the best phone number to reach you?"\n'
        '   - Add [COLLECT_DETERGENT_PHONE] at the END of your response\n\n'
        '3. COLLECT ADDRESS: After they provide phone, ask: "Great. What\'s your shipping address? I\'ll need the street address, city, state, and ZIP code."\n'
        '   - Add [COLLECT_DETERGENT_ADDRESS] at the END of your response\n'
        '   - Listen carefully for: street number, street name, city, state (2-letter if possible), ZIP\n'
        '   - If they give partial info, ask for missing parts before proceeding\n'
        '   - Example: "123 Main Street, Oklahoma City, Oklahoma 73102"\n\n'
        '4. COLLECT PAYMENT: After they provide address, ask: "How would you like to pay? We accept credit card, check, or we can invoice you."\n'
        '   - Add [COLLECT_DETERGENT_PAYMENT] at the END of your response\n'
        '   - Listen for: credit card, check, invoice, purchase order, etc.\n\n'
        '5. CONFIRM & TRANSFER: After payment method, confirm and transfer: "Perfect [name]! I have you at [city, state], paying by [method]. I\'ll get this order processed and connect you with our team right away."\n'
        '   - Add [DETERGENT_ORDER_COMPLETE] at the END of your response\n\n'
        'IMPORTANT ADDRESS PARSING:\n'
        '- People say addresses naturally: "123 Main St, OKC, OK 73102" or "123 Main Street in Oklahoma City Oklahoma, zip 73102"\n'
        '- Extract all parts: street, city, state, ZIP\n'
        '- If anything is unclear or missing, ask politely before proceeding\n\n'
        'IMPORTANT: This special flow ONLY applies when they want to buy DETERGENT/TurboKlean.\n'
        'For other products (T3, T5 washers), use the normal [TRANSFER_TO_SALES] flow.\n'
        'Markers must be EXACTLY as written in square brackets.')

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

    # Conversation settings
    PAUSE_THRESHOLD = float(os.getenv('PAUSE_THRESHOLD', '0.3'))  # Seconds of silence before triggering response
    RESPONSE_TIMEOUT = float(os.getenv('RESPONSE_TIMEOUT', '15.0'))  # Max time for Claude/ElevenLabs

    # Predictive response settings
    PREDICTIVE_RESPONSES = bool(os.getenv('PREDICTIVE_RESPONSES', 'True'))  # Start generating on interim transcripts
    INTERIM_STABILITY_THRESHOLD = int(os.getenv('INTERIM_STABILITY_THRESHOLD', '3'))  # Number of matching interims to trigger

    # Call forwarding
    SALES_FORWARD_NUMBER = os.getenv('SALES_FORWARD_NUMBER', '+18166741783')  # Sales team number

    # QuickBooks Online API
    QUICKBOOKS_CLIENT_ID = os.getenv('QUICKBOOKS_CLIENT_ID')
    QUICKBOOKS_CLIENT_SECRET = os.getenv('QUICKBOOKS_CLIENT_SECRET')
    QUICKBOOKS_REDIRECT_URI = os.getenv('QUICKBOOKS_REDIRECT_URI', 'https://chevroletsneezington.com/qb-callback')
    QUICKBOOKS_ENVIRONMENT = os.getenv('QUICKBOOKS_ENVIRONMENT', 'sandbox')  # 'sandbox' or 'production'
    QUICKBOOKS_REALM_ID = os.getenv('QUICKBOOKS_REALM_ID')  # Company ID (populated after OAuth)
    QUICKBOOKS_REFRESH_TOKEN = os.getenv('QUICKBOOKS_REFRESH_TOKEN')  # Refresh token (populated after OAuth)

    # Database
    DATABASE_URL = os.getenv('DATABASE_URL')

    # Product Configuration
    DETERGENT_PRODUCT_NAME = os.getenv('DETERGENT_PRODUCT_NAME', 'Detergent')  # Exact product name in QuickBooks

    # Flask settings
    PORT = int(os.getenv('PORT', 5000))
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
