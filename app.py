"""
Phone Agent - Twilio + Deepgram + Claude + ElevenLabs
"""
import sys
import json
import base64
import asyncio
import threading
import time
import os
import uuid
from queue import Queue, Empty

from flask import Flask, request, send_file
from flask_sock import Sock
from twilio.twiml.voice_response import VoiceResponse, Start, Connect, Play
from twilio.rest import Client as TwilioClient

from config import Config
from call_manager import call_manager
from deepgram_client import DeepgramClient
from conversation_manager import ConversationManager, ConversationState
from claude_client import ClaudeAgent
from elevenlabs_client import ElevenLabsClient

# Ensure real-time console output
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

# Initialize Flask
app = Flask(__name__)
sock = Sock(app)

# Initialize Twilio client
twilio_client = TwilioClient(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)

# Create temp directory for audio files
TEMP_AUDIO_DIR = os.path.join(os.path.dirname(__file__), 'temp_audio')
os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

# Store active sessions
sessions = {}

# Store conversation state per call (persists across reconnections)
call_conversations = {}  # call_sid -> ConversationManager
call_ai_speaking_until = {}  # call_sid -> timestamp when AI will stop speaking

# Cached responses for common questions (populated at startup)
cached_responses = {}

# Cache persistence directory
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cached_audio')
os.makedirs(CACHE_DIR, exist_ok=True)


def load_cached_responses_from_disk():
    """Load cached responses from disk if they exist"""
    print("[Cache] Checking for saved cache files...")

    # Define common Q&A pairs (metadata)
    common_qa = {
        'price_t5': {
            'keywords': ['how much', 'price', 'cost', 't5', 't 5', 'storm'],
            'response': "The T5 Storm costs $10,000."
        },
        'price_t3': {
            'keywords': ['how much', 'price', 'cost', 't3', 't 3', 'lightning'],
            'response': "The T3 Lightning costs $8,000."
        },
        'location': {
            'keywords': ['where', 'located', 'location', 'headquarter'],
            'response': "TEMCO is headquartered in Oklahoma City."
        },
        'owner': {
            'keywords': ['owner', 'who owns', 'mark', 'who is the'],
            'response': "The owner of TEMCO is Mark Hayworth."
        },
        'contact': {
            'keywords': ['phone', 'number', 'contact', 'reach', 'call'],
            'response': "You can reach TEMCO at 800-245-1869."
        }
    }

    loaded_count = 0
    for key, qa in common_qa.items():
        cache_file = os.path.join(CACHE_DIR, f"{key}.ulaw")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    audio_bytes = f.read()

                cached_responses[key] = {
                    'keywords': qa['keywords'],
                    'response': qa['response'],
                    'audio': audio_bytes
                }
                loaded_count += 1
                print(f"[Cache] ✅ Loaded from disk: {key}")
            except Exception as e:
                print(f"[Cache] ⚠️  Failed to load {key}: {e}")

    if loaded_count > 0:
        print(f"[Cache] Loaded {loaded_count}/{len(common_qa)} responses from disk\n")
        return loaded_count == len(common_qa)
    else:
        print(f"[Cache] No cached files found on disk\n")
        return False


def generate_cached_responses():
    """
    Generate and cache audio responses for common questions
    Called at server startup to pre-generate responses
    """
    print("[Cache] Generating cached responses for common questions...")

    # Define common Q&A pairs
    common_qa = {
        'price_t5': {
            'keywords': ['how much', 'price', 'cost', 't5', 't 5', 'storm'],
            'response': "The T5 Storm costs $10,000."
        },
        'price_t3': {
            'keywords': ['how much', 'price', 'cost', 't3', 't 3', 'lightning'],
            'response': "The T3 Lightning costs $8,000."
        },
        'location': {
            'keywords': ['where', 'located', 'location', 'headquarter'],
            'response': "TEMCO is headquartered in Oklahoma City."
        },
        'owner': {
            'keywords': ['owner', 'who owns', 'mark', 'who is the'],
            'response': "The owner of TEMCO is Mark Hayworth."
        },
        'contact': {
            'keywords': ['phone', 'number', 'contact', 'reach', 'call'],
            'response': "You can reach TEMCO at 800-245-1869."
        }
    }

    try:
        # Check if ElevenLabs is configured
        if not Config.ELEVENLABS_API_KEY:
            print(f"[Cache] ❌ ELEVENLABS_API_KEY not configured!")
            print(f"[Cache] Cache generation skipped - responses will be slow\n")
            return False

        # Create temporary ElevenLabs client
        print(f"[Cache] Creating ElevenLabs client...")
        tts = ElevenLabsClient()

        # Generate audio for each response
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        success_count = 0
        for key, qa in common_qa.items():
            try:
                print(f"[Cache] Generating: {qa['response']}")
                audio_bytes = loop.run_until_complete(tts.text_to_speech(qa['response']))

                if audio_bytes:
                    cached_responses[key] = {
                        'keywords': qa['keywords'],
                        'response': qa['response'],
                        'audio': audio_bytes
                    }

                    # Save to disk for future use
                    cache_file = os.path.join(CACHE_DIR, f"{key}.ulaw")
                    with open(cache_file, 'wb') as f:
                        f.write(audio_bytes)

                    success_count += 1
                    print(f"[Cache] [OK] Cached: {key} ({len(audio_bytes)} bytes)")
                else:
                    print(f"[Cache] [WARNING] Failed: {key} (no audio returned)")

            except Exception as e:
                print(f"[Cache] [ERROR] Error caching {key}: {e}")
                import traceback
                traceback.print_exc()

        loop.close()

        print(f"[Cache] [OK] Successfully cached {success_count}/{len(common_qa)} responses\n")
        return success_count > 0

    except Exception as e:
        print(f"[Cache] [ERROR] Error generating cached responses: {e}")
        import traceback
        traceback.print_exc()
        return False


def convert_phone_text_to_digits(phone_text):
    """
    Convert spoken phone number text to digits

    Args:
        phone_text: Phone number as spoken text (e.g., "five five five one two three four five six seven")

    Returns:
        10-digit phone number string, or None if not enough digits
    """
    import re

    # Mapping of text numbers to digits
    text_to_digit = {
        'zero': '0', 'oh': '0', 'o': '0',
        'one': '1', 'won': '1',
        'two': '2', 'to': '2', 'too': '2',
        'three': '3', 'tree': '3',
        'four': '4', 'for': '4',
        'five': '5',
        'six': '6', 'sics': '6',
        'seven': '7',
        'eight': '8', 'ate': '8',
        'nine': '9', 'niner': '9'
    }

    print(f"[Phone Parser] Converting: '{phone_text}'")

    # IMPORTANT: Deepgram sends duplicates! Take only first sentence to avoid counting repeats
    first_sentence = phone_text.split('.')[0].strip()
    print(f"[Phone Parser] Using first sentence only: '{first_sentence}'")

    # Convert to lowercase and split into words
    words = first_sentence.lower().split()

    # Extract digits
    digits = []

    for word in words:
        # Remove punctuation
        word = word.strip('.,!?')

        # Check if it's already a digit
        if word.isdigit():
            digits.extend(list(word))
        # Check if it's a text number
        elif word in text_to_digit:
            digits.append(text_to_digit[word])

    # Join all digits
    phone_number = ''.join(digits)

    print(f"[Phone Parser] Extracted digits: '{phone_number}' ({len(phone_number)} digits)")

    # Need exactly 10 digits (area code + number)
    if len(phone_number) == 10:
        # Exactly 10 digits - perfect!
        print(f"[Phone Parser] ✓ Result: {phone_number}")
        return phone_number
    elif len(phone_number) < 10:
        print(f"[Phone Parser] ✗ Not enough digits (need 10, got {len(phone_number)})")
        return None
    else:
        # More than 10 - might be repeats or mistakes, don't guess
        print(f"[Phone Parser] ✗ Too many digits (need 10, got {len(phone_number)})")
        return None


def parse_address(address_text):
    """
    Parse address from natural language into components

    Args:
        address_text: Address string from user

    Returns:
        Dict with keys: street, city, state, zip
    """
    import re

    print(f"[Address Parser] Parsing: '{address_text}'")

    # Try to extract zip code (5 digits, possibly with dash and 4 more)
    zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\b', address_text)
    zip_code = zip_match.group(1) if zip_match else ''

    # Try to extract state (2 letter code - uppercase)
    state_match = re.search(r'\b([A-Z]{2})\b', address_text.upper())
    state = state_match.group(1) if state_match else ''

    # If no 2-letter state found, try common state names
    if not state:
        state_names = {
            'oklahoma': 'OK', 'texas': 'TX', 'california': 'CA', 'kansas': 'KS',
            'missouri': 'MO', 'arkansas': 'AR', 'new mexico': 'NM', 'colorado': 'CO'
        }
        text_lower = address_text.lower()
        for full_name, abbrev in state_names.items():
            if full_name in text_lower:
                state = abbrev
                break

    # Remove zip and state from text to isolate street and city
    remaining = address_text
    if zip_code:
        remaining = remaining.replace(zip_code, '')
    if state:
        # Remove state abbreviation
        remaining = re.sub(r'\b' + state + r'\b', '', remaining, flags=re.IGNORECASE)

    # Clean up punctuation and extra spaces
    remaining = remaining.replace(',', ' ').strip()
    remaining = re.sub(r'\s+', ' ', remaining)

    # Split remaining text - usually: street, city
    # Common patterns: "123 Main St Oklahoma City" or "123 Main Street OKC"
    parts = remaining.split()

    # Heuristic: city is usually 1-2 words at the end, street is the rest
    if len(parts) >= 3:
        # Assume last 1-2 words are city
        if len(parts) >= 4:
            street = ' '.join(parts[:-2])
            city = ' '.join(parts[-2:])
        else:
            street = ' '.join(parts[:-1])
            city = parts[-1]
    elif len(parts) == 2:
        street = parts[0]
        city = parts[1]
    elif len(parts) == 1:
        street = parts[0]
        city = ''
    else:
        street = ''
        city = ''

    result = {
        'street': street.strip(),
        'city': city.strip(),
        'state': state,
        'zip': zip_code
    }

    print(f"[Address Parser] Result: {result}")
    return result


def check_cached_response(user_text):
    """
    Check if user's question matches a cached response

    Args:
        user_text: User's spoken text

    Returns:
        dict with 'audio' and 'text' if match found, None otherwise
    """
    print(f"\n[Cache Debug] Checking cache for: '{user_text}'")
    print(f"[Cache Debug] Cache has {len(cached_responses)} responses loaded")

    if not user_text:
        print(f"[Cache Debug] ❌ No user text provided")
        return None

    if not cached_responses:
        print(f"[Cache Debug] ❌ Cache is empty!")
        return None

    text_lower = user_text.lower()
    print(f"[Cache Debug] Lowercased text: '{text_lower}'")

    # Check each cached response
    for key, cached in cached_responses.items():
        # Count keyword matches
        matched_keywords = [keyword for keyword in cached['keywords'] if keyword in text_lower]
        matches = len(matched_keywords)

        print(f"[Cache Debug] Testing '{key}': {matches} matches {matched_keywords}")

        # If multiple keywords match, likely a match
        if matches >= 2:
            print(f"[Cache] 🎯 Match found: {key} (matched: {matched_keywords})")
            return {
                'audio': cached['audio'],
                'text': cached['response'],
                'transfer': False
            }

    print(f"[Cache Debug] ❌ No match found (need 2+ keyword matches)\n")
    return None


def generate_greeting_audio():
    """
    Generate greeting audio file using ElevenLabs
    Creates a permanent greeting file if it doesn't exist
    """
    greeting_path = os.path.join(TEMP_AUDIO_DIR, 'greeting.ulaw')

    # Only generate if file doesn't exist
    if os.path.exists(greeting_path):
        print(f"[Greeting] Using existing greeting audio: {greeting_path}")
        return greeting_path

    print(f"[Greeting] Generating new greeting audio...")

    try:
        # Create temporary ElevenLabs client
        tts = ElevenLabsClient()
        greeting_text = "TEMCO, how can I help you?"

        # Generate audio synchronously at startup
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_bytes = loop.run_until_complete(tts.text_to_speech(greeting_text))
        loop.close()

        if audio_bytes:
            # Save to file
            with open(greeting_path, 'wb') as f:
                f.write(audio_bytes)
            print(f"[Greeting] ✅ Generated greeting audio: {greeting_path}")
            return greeting_path
        else:
            print(f"[Greeting] ❌ Failed to generate greeting audio")
            return None

    except Exception as e:
        print(f"[Greeting] ❌ Error generating greeting: {e}")
        import traceback
        traceback.print_exc()
        return None


@app.route("/")
def home():
    """Health check"""
    return "Phone Agent Running!", 200


@app.route("/audio/<filename>")
def serve_audio(filename):
    """Serve temporary audio files"""
    try:
        file_path = os.path.join(TEMP_AUDIO_DIR, filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='audio/x-mulaw')
        else:
            return "Audio file not found", 404
    except Exception as e:
        print(f"[Audio Server] Error serving {filename}: {e}")
        return "Error serving audio", 500


@app.route("/voice", methods=['POST'])
def voice():
    """Handle incoming calls"""
    print("\n" + "="*80)
    print("INCOMING CALL")
    print("="*80)

    call_sid = request.values.get('CallSid')
    caller = request.values.get('From')

    print(f"Call SID: {call_sid}")
    print(f"From: {caller}")
    print("="*80 + "\n")

    # Create call record
    call_manager.create_call(call_sid, caller)

    # Generate TwiML response
    response = VoiceResponse()

    # Play ElevenLabs greeting instead of Twilio TTS
    greeting_path = os.path.join(TEMP_AUDIO_DIR, 'greeting.ulaw')
    if os.path.exists(greeting_path):
        base_url = Config.WEBSOCKET_URL.replace('wss://', 'https://').replace('/media', '')
        greeting_url = f"{base_url}/audio/greeting.ulaw"
        response.play(greeting_url)
    else:
        # Fallback to Twilio TTS if ElevenLabs greeting doesn't exist
        print(f"[Voice] ⚠️ ElevenLabs greeting not found, using Twilio TTS")
        response.say("TEMCO, how can I help you?", voice='Polly.Joanna')

    # Add brief pause after greeting to let Deepgram reset
    response.pause(length=0.5)

    # Start media stream with inbound audio only (prevents AI echo)
    start = Start()
    stream = start.stream(url=Config.WEBSOCKET_URL)
    # Only capture inbound audio (caller's voice) to prevent echo of AI responses
    stream.parameter(name='track', value='inbound_track')
    response.append(start)

    # Keep call open for conversation (10 minutes max)
    response.pause(length=600)
    response.say("Thank you for calling. Goodbye!", voice='Polly.Joanna')

    return str(response), 200, {'Content-Type': 'text/xml'}


@app.route("/continue-stream", methods=['POST'])
def continue_stream():
    """Re-establish media stream after playing AI response"""
    print("[Continue] Re-establishing media stream")

    # Generate TwiML to re-establish the stream
    response = VoiceResponse()

    # Re-establish media stream with inbound audio only (prevents AI echo)
    start = Start()
    stream = start.stream(url=Config.WEBSOCKET_URL)
    # Only capture inbound audio (caller's voice) to prevent echo of AI responses
    stream.parameter(name='track', value='inbound_track')
    response.append(start)

    # Keep call open for more conversation (10 minutes)
    response.pause(length=600)
    response.say("Thank you for calling. Goodbye!", voice='Polly.Joanna')

    return str(response), 200, {'Content-Type': 'text/xml'}


@sock.route('/media')
def media(ws):
    """Handle WebSocket media stream"""
    print("\n" + "="*80)
    print("WEBSOCKET CONNECTED")
    print("="*80 + "\n")

    session_id = None
    call_sid = None

    try:
        while True:
            message = ws.receive()
            if message is None:
                break

            data = json.loads(message)
            event = data.get('event')

            if event == 'start':
                session_id = id(ws)
                call_sid = data['start']['callSid']
                stream_sid = data['streamSid']

                print(f"[Stream Start] Call: {call_sid}")
                print(f"[Stream Start] Stream: {stream_sid}")

                # Reuse existing conversation manager if available (preserves history across reconnections)
                if call_sid in call_conversations:
                    print(f"[Stream Start] ✅ Reusing existing conversation state")
                    conv_mgr = call_conversations[call_sid]
                else:
                    print(f"[Stream Start] Creating new conversation state")
                    conv_mgr = ConversationManager(call_sid)
                    call_conversations[call_sid] = conv_mgr

                # Create Claude agent with existing conversation history (if any)
                claude = ClaudeAgent(conversation_history=conv_mgr.get_conversation_history())
                print(f"[Stream Start] Claude agent initialized with {len(conv_mgr.get_conversation_history())} messages in history")

                print()

                # Create session with AI components
                sessions[session_id] = {
                    'call_sid': call_sid,
                    'stream_sid': stream_sid,
                    'ws': ws,  # Store WebSocket for sending audio back
                    'audio_queue': Queue(),
                    'running': True,
                    'audio_received_count': 0,
                    'conversation_manager': conv_mgr,
                    'claude_agent': claude,
                    'elevenlabs_client': ElevenLabsClient(),
                }

                # Start Deepgram worker
                thread = threading.Thread(
                    target=deepgram_worker,
                    args=(session_id, call_sid),
                    daemon=True
                )
                thread.start()

            elif event == 'media':
                if session_id in sessions:
                    # Decode audio and add to queue
                    payload = data['media']['payload']
                    audio = base64.b64decode(payload)

                    sessions[session_id]['audio_received_count'] += 1

                    # Log first audio chunk
                    if sessions[session_id]['audio_received_count'] == 1:
                        print(f"[WebSocket] First audio chunk: {len(audio)} bytes\n")

                    try:
                        sessions[session_id]['audio_queue'].put_nowait(audio)
                    except:
                        pass  # Skip if queue full

            elif event == 'stop':
                print(f"\n[Stream Stop] Call: {call_sid}\n")
                if session_id in sessions:
                    sessions[session_id]['running'] = False
                break

    except Exception as e:
        print(f"[WebSocket] Error: {e}")

    finally:
        # Cleanup
        if session_id in sessions:
            audio_received = sessions[session_id].get('audio_received_count', 0)
            print(f"[WebSocket] Received {audio_received} audio chunks from Twilio")
            sessions[session_id]['running'] = False
            session_call_sid = sessions[session_id]['call_sid']
            del sessions[session_id]

            # Only clean up call state if no other sessions exist for this call
            remaining_sessions = [s for s in sessions.values() if s.get('call_sid') == session_call_sid]
            if not remaining_sessions:
                print(f"[WebSocket] Last session for call {session_call_sid}, cleaning up call state")
                # Clean up call manager
                try:
                    call_manager.end_call(session_call_sid)
                except KeyError:
                    pass  # Already cleaned up

                # Clean up conversation state (preserves history for potential reconnects within ~30s)
                # We keep these for a bit longer in case of quick reconnects
                # In production, you'd want a more sophisticated cleanup strategy

        print("[WebSocket] Disconnected\n")


def transfer_call(call_sid, phone_number, announcement_text="Transferring you now."):
    """
    Transfer call to another phone number

    Args:
        call_sid: Twilio call SID
        phone_number: Phone number to transfer to (E.164 format)
        announcement_text: What to say before transferring
    """
    try:
        print(f"\n[Transfer] Transferring call {call_sid} to {phone_number}")
        print(f"[Transfer] Announcement: '{announcement_text}'")

        # Create TwiML to announce transfer and dial
        twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">{announcement_text}</Say>
    <Dial>{phone_number}</Dial>
</Response>'''

        # Update the call with transfer TwiML
        twilio_client.calls(call_sid).update(twiml=twiml)

        print(f"[Transfer] ✅ Call transfer initiated to {phone_number}\n")
        return True

    except Exception as e:
        print(f"[Transfer] ❌ Error transferring call: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_audio_via_websocket(session_id, audio_bytes):
    """
    Send audio directly through WebSocket (fastest method)

    Args:
        session_id: Session ID
        audio_bytes: mulaw audio bytes to send
    """
    if session_id not in sessions:
        print(f"[WebSocket Audio] Session {session_id} not found")
        return False

    session = sessions[session_id]
    ws = session.get('ws')
    stream_sid = session.get('stream_sid')

    if not ws or not stream_sid:
        print(f"[WebSocket Audio] No active WebSocket or stream_sid")
        return False

    try:
        # Calculate audio duration for echo prevention
        audio_duration = len(audio_bytes) / 8000.0
        call_sid = session['call_sid']
        call_ai_speaking_until[call_sid] = time.time() + audio_duration + 0.5

        print(f"[WebSocket Audio] Streaming {len(audio_bytes)} bytes ({audio_duration:.1f}s)")

        # Twilio expects chunks of 160 bytes (20ms of mulaw audio at 8kHz)
        chunk_size = 160
        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i:i+chunk_size]

            # Encode as base64
            payload = base64.b64encode(chunk).decode('utf-8')

            # Send media message to Twilio
            # NOTE: This may not work - Twilio Media Streams may not support sending audio back
            message = json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": payload,
                    "track": "outbound"  # Specify outbound track
                }
            })

            ws.send(message)

        print(f"[WebSocket Audio] ✅ Streamed audio successfully")
        return True

    except Exception as e:
        print(f"[WebSocket Audio] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_audio_to_twilio(call_sid, audio_bytes):
    """
    Send audio back to Twilio caller using REST API

    Args:
        call_sid: Twilio call SID
        audio_bytes: mulaw audio bytes to send
    """
    try:
        # Calculate audio duration (mulaw is 8kHz, 8-bit, mono)
        # Each byte = 1 sample, so duration = bytes / 8000 Hz
        audio_duration = len(audio_bytes) / 8000.0
        # Add 1 second buffer for network delay and processing
        ai_speaking_duration = audio_duration + 1.0

        # Mark when AI will stop speaking
        call_ai_speaking_until[call_sid] = time.time() + ai_speaking_duration

        print(f"[Twilio] Audio duration: {audio_duration:.1f}s (will ignore transcripts until {time.strftime('%H:%M:%S', time.localtime(call_ai_speaking_until[call_sid]))})")

        # Generate unique filename
        filename = f"{uuid.uuid4()}.ulaw"
        file_path = os.path.join(TEMP_AUDIO_DIR, filename)

        # Save audio to temporary file
        with open(file_path, 'wb') as f:
            f.write(audio_bytes)

        # Construct public URL (use cloudflare tunnel URL base)
        # Extract base URL from websocket URL
        base_url = Config.WEBSOCKET_URL.replace('wss://', 'https://').replace('/media', '')
        audio_url = f"{base_url}/audio/{filename}"
        continue_url = f"{base_url}/continue-stream"

        print(f"[Twilio] Saved audio to: {filename}")
        print(f"[Twilio] Audio URL: {audio_url}")

        # Update the call to play the audio using TwiML, then redirect to continue stream
        twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{audio_url}</Play>
    <Redirect>{continue_url}</Redirect>
</Response>'''

        # Use Twilio REST API to update the call
        twilio_client.calls(call_sid).update(twiml=twiml)

        print(f"[Twilio] Sent {len(audio_bytes)} bytes of audio via REST API")

        # Schedule cleanup of temp file after 60 seconds
        def cleanup_audio_file():
            time.sleep(60)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"[Twilio] Cleaned up {filename}")
            except Exception as e:
                print(f"[Twilio] Error cleaning up {filename}: {e}")

        cleanup_thread = threading.Thread(target=cleanup_audio_file, daemon=True)
        cleanup_thread.start()

    except Exception as e:
        print(f"[Twilio] Error sending audio: {e}")
        import traceback
        traceback.print_exc()


def detect_detergent_order_intent(user_text):
    """
    Keyword-based detection for detergent order requests
    Returns True if user text indicates they want to order detergent

    Args:
        user_text: The user's spoken text

    Returns:
        bool: True if detergent order keywords detected
    """
    if not user_text:
        return False

    text_lower = user_text.lower()

    # Detergent order keywords (from config.py prompt)
    # IMPORTANT: These are checked BEFORE transfer keywords, so be specific
    detergent_keywords = [
        'order detergent',
        'buy detergent',
        'purchase detergent',
        'want to order more detergent',
        'want to buy more detergent',  # Added
        'want to buy detergent',         # Added
        'buy more detergent',            # Added
        'purchase more detergent',       # Added
        'order more detergent',
        'order turboklean',
        'buy turboklean',
        'need more detergent',
        'want more detergent',
        'want to order detergent',
        'like to order detergent',
        'like to buy detergent',         # Added
        'need detergent',
        'get detergent',
        'get more detergent',
    ]

    # Check for detergent order keywords
    for keyword in detergent_keywords:
        if keyword in text_lower:
            print(f"[Detergent Detection] [DETECTED] Keyword match: '{keyword}'")
            return True

    return False


def detect_transfer_intent(user_text):
    """
    Keyword-based fallback detection for transfer requests
    Returns True if user text indicates they want to be transferred to sales

    Args:
        user_text: The user's spoken text

    Returns:
        bool: True if transfer keywords detected
    """
    if not user_text:
        return False

    text_lower = user_text.lower()

    # Transfer request keywords
    transfer_keywords = [
        'transfer me',
        'transfer to sales',
        'connect me to sales',
        'speak to sales',
        'talk to sales',
        'speak with sales',
        'talk with sales',
    ]

    # Buying/purchasing keywords
    buying_keywords = [
        'want to buy',
        'want to purchase',
        'like to buy',
        'like to purchase',
        'place an order',
        'make a purchase',
        'ready to buy',
        'ready to purchase',
    ]

    # Check for explicit transfer requests
    for keyword in transfer_keywords:
        if keyword in text_lower:
            print(f"[Transfer Detection] [DETECTED] Keyword match: '{keyword}'")
            return True

    # Check for buying intent
    for keyword in buying_keywords:
        if keyword in text_lower:
            print(f"[Transfer Detection] [DETECTED] Buying intent: '{keyword}'")
            return True

    return False


async def handle_ai_response(session_id):
    """
    Handle AI response generation and playback

    Args:
        session_id: Session ID
    """
    if session_id not in sessions:
        return

    session = sessions[session_id]
    conv_mgr = session['conversation_manager']
    claude = session['claude_agent']
    tts = session['elevenlabs_client']
    call_sid = session['call_sid']

    try:
        # Mark AI as speaking (for barge-in detection)
        conv_mgr.start_ai_response()

        # Get user's text
        user_text = conv_mgr.get_user_text()
        print(f"\n[AI] Processing user input: '{user_text}'")

        # CRITICAL: Check for detergent order intent BEFORE calling Claude
        # This bypasses Claude's unreliable prompt following
        detergent_order_detected = detect_detergent_order_intent(user_text)
        forced_response = None
        keyword_transfer_detected = False  # Initialize to avoid UnboundLocalError

        if detergent_order_detected and not conv_mgr.collecting_detergent_info:
            print(f"[AI] [OVERRIDE] Detergent order detected! Forcing workflow start, bypassing Claude.")
            # Force the first step of the detergent workflow
            forced_response = "I can help with that. May I have your name please? [COLLECT_DETERGENT_NAME]"
            print(f"[AI] [OVERRIDE] Forced response: '{forced_response}'\n")

        # State-based forcing: If we're in the middle of collecting detergent info,
        # force the correct next prompt based on what we've collected so far
        # COLLECT PIECE BY PIECE: name → phone → street → city → state → ZIP → payment → quantity
        elif conv_mgr.collecting_detergent_info:
            if not conv_mgr.detergent_customer_name:
                # User just provided their name, store it and ask for phone
                print(f"[AI] [OVERRIDE] State: Name provided, asking for phone")
                # Take only the first sentence to avoid duplicates from Deepgram
                name = user_text.strip().split('.')[0].strip()
                conv_mgr.set_detergent_customer_name(name)
                print(f"[AI] [OVERRIDE] Stored name: {name}")
                forced_response = f"Thank you {name}. What's the best phone number to reach you? [COLLECT_DETERGENT_PHONE]"
            elif not conv_mgr.detergent_customer_phone:
                # User is providing phone number - convert text to digits and validate
                print(f"[AI] [OVERRIDE] State: Phone provided, validating...")
                phone_number = convert_phone_text_to_digits(user_text.strip())

                if phone_number:
                    # We have a complete 10-digit phone number
                    conv_mgr.set_detergent_customer_phone(phone_number)
                    print(f"[AI] [OVERRIDE] Stored phone: {phone_number}")
                    forced_response = "Great. What's the street address? [COLLECT_DETERGENT_ADDRESS]"
                else:
                    # Not enough digits - ask them to repeat
                    print(f"[AI] [OVERRIDE] Phone incomplete, asking to repeat")
                    forced_response = "I didn't catch all of that. Could you give me the full phone number with area code? [COLLECT_DETERGENT_PHONE]"
            elif not conv_mgr.detergent_address_street:
                # User is providing street address
                print(f"[AI] [OVERRIDE] State: Street provided, asking for city")
                street = user_text.strip().split('.')[0].strip()
                conv_mgr.detergent_address_street = street
                print(f"[AI] [OVERRIDE] Stored street: {street}")
                forced_response = "Got it. What city? [COLLECT_DETERGENT_ADDRESS]"
            elif not conv_mgr.detergent_address_city:
                # User is providing city
                print(f"[AI] [OVERRIDE] State: City provided, asking for state")
                city = user_text.strip().split('.')[0].strip()
                conv_mgr.detergent_address_city = city
                print(f"[AI] [OVERRIDE] Stored city: {city}")
                forced_response = "And the state? [COLLECT_DETERGENT_ADDRESS]"
            elif not conv_mgr.detergent_address_state:
                # User is providing state
                print(f"[AI] [OVERRIDE] State: State provided, asking for ZIP")
                state_text = user_text.strip().split('.')[0].strip()
                # Try to parse state (could be "Oklahoma" or "OK")
                state_names = {
                    'oklahoma': 'OK', 'texas': 'TX', 'california': 'CA', 'kansas': 'KS',
                    'missouri': 'MO', 'arkansas': 'AR', 'new mexico': 'NM', 'colorado': 'CO'
                }
                state_lower = state_text.lower()
                if len(state_text) == 2:
                    state = state_text.upper()
                elif state_lower in state_names:
                    state = state_names[state_lower]
                else:
                    state = state_text  # Store as-is if we can't parse
                conv_mgr.detergent_address_state = state
                print(f"[AI] [OVERRIDE] Stored state: {state}")
                forced_response = "And the ZIP code? [COLLECT_DETERGENT_ADDRESS]"
            elif not conv_mgr.detergent_address_zip:
                # User is providing ZIP code
                print(f"[AI] [OVERRIDE] State: ZIP provided, asking for payment")
                zip_text = user_text.strip()
                # Extract 5 digits from text (could be "seven three one zero eight" or "73108")
                import re
                # First try to find existing digits
                zip_match = re.search(r'\b(\d{5})\b', zip_text)
                if zip_match:
                    zip_code = zip_match.group(1)
                else:
                    # Try to convert text to digits (reuse phone converter logic)
                    digits = convert_phone_text_to_digits(zip_text + "     ")  # Pad to avoid "too few digits" error
                    if digits and len(digits) >= 5:
                        zip_code = digits[:5]
                    else:
                        zip_code = zip_text.split('.')[0].strip()  # Store as-is if we can't parse
                conv_mgr.detergent_address_zip = zip_code
                print(f"[AI] [OVERRIDE] Stored ZIP: {zip_code}")
                forced_response = "Perfect. How would you like to pay? We accept credit card, check, or we can invoice you. [COLLECT_DETERGENT_PAYMENT]"
            elif not conv_mgr.detergent_payment_method:
                # User is providing payment method - confirm and ask for quantity
                print(f"[AI] [OVERRIDE] State: Payment provided, confirming details and asking for quantity")
                payment = user_text.strip().split('.')[0].strip()  # Take first sentence
                conv_mgr.set_detergent_payment(payment)
                print(f"[AI] [OVERRIDE] Stored payment: {payment}")
                # Create confirmation message
                forced_response = f"Great! Let me confirm: {conv_mgr.detergent_customer_name} at {conv_mgr.detergent_address_city}, {conv_mgr.detergent_address_state}, paying by {payment}. How many units would you like to order? [COLLECT_DETERGENT_QUANTITY]"
            elif conv_mgr.detergent_quantity is None:
                # User is providing quantity - parse and create invoice
                print(f"[AI] [OVERRIDE] State: Quantity provided, completing order")
                # Extract number from text
                import re
                # Try to find a number
                number_match = re.search(r'\b(\d+)\b', user_text)
                if number_match:
                    quantity = int(number_match.group(1))
                else:
                    # Try text numbers
                    text_numbers = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
                                   'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
                    words = user_text.lower().split()
                    quantity = 1  # Default to 1
                    for word in words:
                        if word in text_numbers:
                            quantity = text_numbers[word]
                            break
                conv_mgr.set_detergent_quantity(quantity)
                print(f"[AI] [OVERRIDE] Stored quantity: {quantity}")
                forced_response = f"Perfect! Is there anything else I can help you with today? [DETERGENT_ORDER_COMPLETE]"

        # Use forced response or get Claude's response
        if forced_response:
            ai_text = forced_response
        else:
            # FALLBACK: Check for transfer intent via keywords (safety net if Claude doesn't trigger)
            keyword_transfer_detected = detect_transfer_intent(user_text)
            if keyword_transfer_detected:
                print(f"[AI] [DETECTED] Fallback transfer detection activated!")

            # Get Claude's response
            print(f"[AI] Calling Claude...")
            ai_text = await claude.get_response(user_text)
            print(f"[AI] Claude responded: '{ai_text}'\n")

        # Check for detergent order markers
        collect_name = '[COLLECT_DETERGENT_NAME]' in ai_text
        collect_phone = '[COLLECT_DETERGENT_PHONE]' in ai_text
        collect_address = '[COLLECT_DETERGENT_ADDRESS]' in ai_text
        collect_payment = '[COLLECT_DETERGENT_PAYMENT]' in ai_text
        detergent_complete = '[DETERGENT_ORDER_COMPLETE]' in ai_text

        # Handle detergent order flow
        # NOTE: State-based forcing already stores data, so these are fallbacks for Claude-generated markers
        if collect_name:
            print(f"[AI] 🧴 Starting detergent order - collecting name")
            conv_mgr.start_collecting_detergent_info()

        elif collect_phone:
            # Only store name if not already stored (fallback for Claude-generated markers)
            if not conv_mgr.detergent_customer_name:
                print(f"[AI] 🧴 Collecting phone number (storing name from previous response)")
                conv_mgr.set_detergent_customer_name(user_text.strip())
            else:
                print(f"[AI] 🧴 Collecting phone number (name already stored)")

        elif collect_address:
            # Only store phone if not already stored (fallback for Claude-generated markers)
            if not conv_mgr.detergent_customer_phone:
                print(f"[AI] 🧴 Collecting shipping address (storing phone from previous response)")
                conv_mgr.set_detergent_customer_phone(user_text.strip())
            else:
                print(f"[AI] 🧴 Collecting shipping address (phone already stored)")

        elif collect_payment:
            # Only store address if not already stored (fallback for Claude-generated markers)
            if not conv_mgr.detergent_address_street:
                print(f"[AI] 🧴 Collecting payment method (storing address from previous response)")
                parsed_address = parse_address(user_text.strip())
                conv_mgr.set_detergent_address(
                    street=parsed_address['street'],
                    city=parsed_address['city'],
                    state=parsed_address['state'],
                    zip_code=parsed_address['zip']
                )
                print(f"[AI] 🧴 Address: {parsed_address['street']}, {parsed_address['city']}, {parsed_address['state']} {parsed_address['zip']}")
            else:
                print(f"[AI] 🧴 Collecting payment method (address already stored)")

        elif detergent_complete:
            # Only store payment if not already stored (fallback for Claude-generated markers)
            if not conv_mgr.detergent_payment_method:
                print(f"[AI] 🧴 Detergent order complete (storing payment from previous response)")
                payment_method = user_text.strip()
                conv_mgr.set_detergent_payment(payment_method)
            else:
                print(f"[AI] 🧴 Detergent order complete (payment already stored)")

            # Get complete order data
            order_data = conv_mgr.get_full_detergent_order()
            print(f"[AI] 🧴 Complete Order:")
            print(f"     Name: {order_data['name']}")
            print(f"     Phone: {order_data['phone']}")
            print(f"     Address: {order_data['address_street']}, {order_data['address_city']}, {order_data['address_state']} {order_data['address_zip']}")
            print(f"     Payment: {order_data['payment_method']}")

            # Save to database
            try:
                from database import create_order
                order_id = create_order(order_data)
                print(f"[AI] 🧴 Saved to database: Order ID {order_id}")
            except Exception as e:
                print(f"[AI] 🧴 ❌ Database save failed: {e}")
                order_id = None

            # Sync to QuickBooks (if database save succeeded)
            if order_id:
                try:
                    from quickbooks_client import QuickBooksClient
                    qb = QuickBooksClient()

                    # Create/update customer
                    qb_customer_id = qb.get_or_create_customer(
                        name=order_data['name'],
                        phone=order_data['phone'],
                        address={
                            'street': order_data['address_street'],
                            'city': order_data['address_city'],
                            'state': order_data['address_state'],
                            'zip': order_data['address_zip']
                        }
                    )

                    # Create invoice with user-specified quantity
                    invoice = qb.create_invoice(
                        customer_id=qb_customer_id,
                        product_name=Config.DETERGENT_PRODUCT_NAME,
                        quantity=order_data['quantity'],
                        payment_method=order_data['payment_method']
                    )

                    # Update database
                    from database import update_sync_status
                    update_sync_status(
                        order_id=order_id,
                        status='synced',
                        qb_data={
                            'customer_id': qb_customer_id,
                            'invoice_id': invoice.Id,
                            'invoice_number': invoice.DocNumber
                        },
                        error=None
                    )

                    print(f"[AI] 🧴 ✅ Synced to QuickBooks - Invoice #{invoice.DocNumber}")

                except Exception as e:
                    print(f"[AI] 🧴 ❌ QuickBooks sync failed: {e}")
                    import traceback
                    traceback.print_exc()

                    # Update database with failure
                    try:
                        from database import update_sync_status
                        update_sync_status(order_id=order_id, status='failed', qb_data=None, error=str(e))
                    except:
                        pass

        # Check for transfer request from Claude
        transfer_requested_by_claude = '[TRANSFER_TO_SALES]' in ai_text

        # Combine Claude's decision with keyword fallback
        # Note: Detergent order completion does NOT trigger transfer - order is already saved to QuickBooks
        transfer_requested = transfer_requested_by_claude or keyword_transfer_detected

        # Remove markers from spoken text
        spoken_text = ai_text.replace('[TRANSFER_TO_SALES]', '').strip()
        spoken_text = spoken_text.replace('[COLLECT_DETERGENT_NAME]', '').strip()
        spoken_text = spoken_text.replace('[COLLECT_DETERGENT_PHONE]', '').strip()
        spoken_text = spoken_text.replace('[COLLECT_DETERGENT_ADDRESS]', '').strip()
        spoken_text = spoken_text.replace('[COLLECT_DETERGENT_PAYMENT]', '').strip()
        spoken_text = spoken_text.replace('[COLLECT_DETERGENT_QUANTITY]', '').strip()
        spoken_text = spoken_text.replace('[DETERGENT_ORDER_COMPLETE]', '').strip()

        # If keyword detected transfer but Claude didn't trigger it, override response
        if keyword_transfer_detected and not transfer_requested_by_claude:
            print(f"[AI] ⚠️ Claude didn't trigger transfer, using fallback override")
            spoken_text = "I'd be happy to connect you with our sales team right now."

        # Convert to speech
        print(f"[AI] Generating speech...")
        audio_bytes = await tts.text_to_speech(spoken_text)

        if audio_bytes:
            # Send audio to caller via REST API
            print(f"[AI] Playing audio to caller...")
            send_audio_to_twilio(call_sid, audio_bytes)
            print(f"[AI] ✅ Response delivered!\n")
        else:
            # Fallback: use Twilio's built-in TTS
            print(f"[AI] ⚠️ TTS failed, using text fallback")
            # Note: Twilio's <Say> can't be used mid-stream, so we skip audio

        # Mark conversation complete
        conv_mgr.finish_ai_response(spoken_text)

        # Log AI response to call manager (as final transcript)
        call_manager.add_transcript(call_sid, spoken_text, is_final=True, speaker='AI')

        # Handle transfer if requested (by Claude OR by keyword fallback)
        if transfer_requested:
            if transfer_requested_by_claude:
                print(f"[AI] 🔄 Transfer to sales requested by Claude!")
            else:
                print(f"[AI] 🔄 Transfer to sales triggered by keyword fallback!")
            # Give a moment for the announcement to finish playing
            await asyncio.sleep(2)
            # Transfer the call
            transfer_call(call_sid, Config.SALES_FORWARD_NUMBER)
            print(f"[AI] Transfer initiated, ending AI session\n")

    except Exception as e:
        print(f"[AI] ❌ Error: {e}")
        import traceback
        traceback.print_exc()


def deepgram_worker(session_id, call_sid):
    """Worker thread for Deepgram connection and conversation management"""

    if session_id not in sessions:
        return

    conv_mgr = sessions[session_id]['conversation_manager']

    # Storage for predictive response
    predictive_response_data = {
        'task': None,
        'result': None,
        'text': None
    }

    def on_predictive_trigger(interim_text):
        """Callback when stable interim detected - start generating response early"""
        nonlocal predictive_response_data

        # Cancel any existing predictive response
        if predictive_response_data['task'] and not predictive_response_data['task'].done():
            predictive_response_data['task'].cancel()

        # Start new predictive response generation
        async def generate_predictive():
            try:
                print(f"[Predictive] Generating response for: '{interim_text}'")
                claude = sessions[session_id]['claude_agent']
                tts = sessions[session_id]['elevenlabs_client']

                # Get Claude's response
                ai_text = await claude.get_response(interim_text)
                print(f"[Predictive] Claude ready: '{ai_text[:50]}...'")

                # Check for transfer and detergent markers
                transfer_requested = '[TRANSFER_TO_SALES]' in ai_text
                detergent_complete = '[DETERGENT_ORDER_COMPLETE]' in ai_text

                # Remove all markers from spoken text
                spoken_text = ai_text.replace('[TRANSFER_TO_SALES]', '').strip()
                spoken_text = spoken_text.replace('[COLLECT_DETERGENT_NAME]', '').strip()
                spoken_text = spoken_text.replace('[COLLECT_DETERGENT_PHONE]', '').strip()
                spoken_text = spoken_text.replace('[DETERGENT_ORDER_COMPLETE]', '').strip()

                # Generate audio
                audio_bytes = await tts.text_to_speech(spoken_text)

                if audio_bytes:
                    predictive_response_data['result'] = {
                        'audio': audio_bytes,
                        'text': spoken_text,
                        'transfer': transfer_requested or detergent_complete,
                        'interim_text': interim_text
                    }
                    print(f"[Predictive] ✅ Response ready in advance!")

            except asyncio.CancelledError:
                print(f"[Predictive] ⚠️ Cancelled (user still talking)")
            except Exception as e:
                print(f"[Predictive] ❌ Error: {e}")

        # Create and store task
        loop = asyncio.get_event_loop()
        predictive_response_data['task'] = loop.create_task(generate_predictive())

    # Set up predictive response callback
    conv_mgr.on_predictive_trigger = on_predictive_trigger

    def on_transcript(text, is_final):
        """Callback when transcript received"""
        # Check if AI is currently speaking - if so, ignore transcripts (this is echo)
        current_time = time.time()
        if call_sid in call_ai_speaking_until:
            if current_time < call_ai_speaking_until[call_sid]:
                # AI is still speaking, ignore this transcript to prevent echo
                if text:  # Only log if there's actual text
                    print(f"[Echo Filter] Ignoring transcript during AI speaking: '{text}'")
                return
            else:
                # AI finished speaking, remove the marker
                del call_ai_speaking_until[call_sid]
                print(f"[Echo Filter] AI finished speaking, resuming transcript processing")

        # Send to old call manager for logging (with speaker label)
        call_manager.add_transcript(call_sid, text, is_final, speaker='Caller')

        # Send to conversation manager for pause detection
        conv_mgr.add_transcript(text, is_final)

    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run():
        # Connect to Deepgram
        client = DeepgramClient(on_transcript)
        connected = await client.connect()

        if not connected:
            print("[Deepgram] Failed to connect!")
            return

        # Process audio queue and check for pauses
        audio_count = 0
        last_pause_check = time.time()

        while sessions.get(session_id, {}).get('running', False):
            try:
                # Process audio from queue
                try:
                    audio = sessions[session_id]['audio_queue'].get(timeout=0.1)
                    await client.send(audio)

                    audio_count += 1
                    if audio_count == 1:
                        print("[Deepgram] Receiving audio...\n")

                    # CRITICAL FIX: Pace audio at 20ms intervals (mulaw 160 bytes = 20ms)
                    # Sending too fast causes Deepgram to buffer heavily and delay responses
                    await asyncio.sleep(0.02)

                except Empty:
                    await asyncio.sleep(0.01)

                # Check for pause detection every 0.5 seconds
                current_time = time.time()
                if current_time - last_pause_check >= 0.5:
                    last_pause_check = current_time

                    # Check if user has paused speaking
                    if conv_mgr.check_for_pause():
                        response_start_time = time.time()
                        user_text = conv_mgr.get_user_text()
                        print(f"\n[TIMING] Response generation starting for: '{user_text}'")

                        # PRIORITY 1: Check cached responses (instant)
                        cache_check_start = time.time()
                        cached_result = check_cached_response(user_text)
                        cache_check_duration = time.time() - cache_check_start
                        print(f"[TIMING] Cache check took: {cache_check_duration:.3f}s")

                        if cached_result:
                            print(f"[Conversation] 💨 Using cached response!")
                            conv_mgr.start_ai_response()

                            audio_send_start = time.time()
                            send_audio_to_twilio(call_sid, cached_result['audio'])
                            audio_send_duration = time.time() - audio_send_start
                            print(f"[TIMING] Audio send took: {audio_send_duration:.3f}s")

                            conv_mgr.finish_ai_response(cached_result['text'])
                            call_manager.add_transcript(call_sid, cached_result['text'], is_final=True, speaker='AI')

                            total_duration = time.time() - response_start_time
                            print(f"[TIMING] ✅ Total cached response time: {total_duration:.3f}s\n")

                            # Clear predictive response if any
                            predictive_response_data['result'] = None

                        # PRIORITY 2: Check if predictive response is ready
                        elif predictive_response_data['result']:
                            print(f"[Conversation] ⚡ Using pre-generated response!")
                            result = predictive_response_data['result']

                            # Play the pre-generated audio
                            conv_mgr.start_ai_response()

                            audio_send_start = time.time()
                            send_audio_to_twilio(call_sid, result['audio'])
                            audio_send_duration = time.time() - audio_send_start
                            print(f"[TIMING] Audio send took: {audio_send_duration:.3f}s")

                            conv_mgr.finish_ai_response(result['text'])
                            call_manager.add_transcript(call_sid, result['text'], is_final=True, speaker='AI')

                            # Handle transfer if needed
                            if result['transfer']:
                                await asyncio.sleep(2)
                                transfer_call(call_sid, Config.SALES_FORWARD_NUMBER)

                            # Clear predictive response
                            predictive_response_data['result'] = None

                            total_duration = time.time() - response_start_time
                            print(f"[TIMING] ✅ Total predictive response time: {total_duration:.3f}s\n")

                        else:
                            # No predictive response ready, generate normally
                            print(f"[Conversation] Triggering AI response (no cache/predictive match)...")
                            ai_start = time.time()
                            await handle_ai_response(session_id)
                            ai_duration = time.time() - ai_start

                            total_duration = time.time() - response_start_time
                            print(f"[TIMING] AI response generation took: {ai_duration:.3f}s")
                            print(f"[TIMING] ✅ Total response time: {total_duration:.3f}s\n")

            except Exception as e:
                print(f"[Deepgram] Error: {e}")
                import traceback
                traceback.print_exc()
                break



        # Close connection
        print(f"[Deepgram] Processed {audio_count} audio chunks")
        await client.close()

    loop.run_until_complete(run())
    loop.close()


@app.route("/qb-connect")
def qb_connect():
    """Initiate QuickBooks OAuth flow"""
    try:
        from intuitlib.client import AuthClient
        from intuitlib.enums import Scopes

        auth_client = AuthClient(
            client_id=Config.QUICKBOOKS_CLIENT_ID,
            client_secret=Config.QUICKBOOKS_CLIENT_SECRET,
            redirect_uri=Config.QUICKBOOKS_REDIRECT_URI,
            environment=Config.QUICKBOOKS_ENVIRONMENT
        )

        auth_url = auth_client.get_authorization_url([Scopes.ACCOUNTING])

        return f'''
        <html>
        <head><title>Connect to QuickBooks</title></head>
        <body style="font-family: Arial; padding: 40px;">
            <h1>Connect Phone Agent to QuickBooks Online</h1>
            <p>Click the button below to authorize this app to create customers and invoices in QuickBooks.</p>
            <p><a href="{auth_url}" style="display: inline-block; padding: 15px 30px; background: #2ca01c; color: white; text-decoration: none; border-radius: 5px; font-size: 16px;">Connect to QuickBooks</a></p>
            <p style="color: #666; font-size: 14px;">Environment: {Config.QUICKBOOKS_ENVIRONMENT}</p>
        </body>
        </html>
        '''
    except Exception as e:
        return f'''
        <html>
        <body style="font-family: Arial; padding: 40px;">
            <h1>Error</h1>
            <p style="color: red;">Failed to initiate QuickBooks connection: {str(e)}</p>
            <p>Make sure QUICKBOOKS_CLIENT_ID and QUICKBOOKS_CLIENT_SECRET are set in .env</p>
        </body>
        </html>
        ''', 500


@app.route("/qb-callback")
def qb_callback():
    """Handle QuickBooks OAuth callback"""
    try:
        from intuitlib.client import AuthClient
        import os

        auth_code = request.args.get('code')
        realm_id = request.args.get('realmId')
        error = request.args.get('error')

        if error:
            return f'''
            <html>
            <body style="font-family: Arial; padding: 40px;">
                <h1>Authorization Failed</h1>
                <p style="color: red;">Error: {error}</p>
                <p><a href="/qb-connect">Try again</a></p>
            </body>
            </html>
            ''', 400

        if not auth_code:
            return "Error: No authorization code received", 400

        auth_client = AuthClient(
            client_id=Config.QUICKBOOKS_CLIENT_ID,
            client_secret=Config.QUICKBOOKS_CLIENT_SECRET,
            redirect_uri=Config.QUICKBOOKS_REDIRECT_URI,
            environment=Config.QUICKBOOKS_ENVIRONMENT
        )

        # Exchange code for tokens
        auth_client.get_bearer_token(auth_code, realm_id=realm_id)
        refresh_token = auth_client.refresh_token

        # Save to .env file
        env_path = os.path.join(os.path.dirname(__file__), '.env')

        # Read existing .env
        with open(env_path, 'r') as f:
            lines = f.readlines()

        # Update QUICKBOOKS_REALM_ID and QUICKBOOKS_REFRESH_TOKEN
        realm_found = False
        token_found = False

        with open(env_path, 'w') as f:
            for line in lines:
                if line.startswith('QUICKBOOKS_REALM_ID='):
                    f.write(f'QUICKBOOKS_REALM_ID={realm_id}\n')
                    realm_found = True
                elif line.startswith('QUICKBOOKS_REFRESH_TOKEN='):
                    f.write(f'QUICKBOOKS_REFRESH_TOKEN={refresh_token}\n')
                    token_found = True
                else:
                    f.write(line)

            # Add if not found
            if not realm_found:
                f.write(f'\nQUICKBOOKS_REALM_ID={realm_id}\n')
            if not token_found:
                f.write(f'QUICKBOOKS_REFRESH_TOKEN={refresh_token}\n')

        return f'''
        <html>
        <body style="font-family: Arial; padding: 40px;">
            <h1 style="color: #2ca01c;">QuickBooks Connected Successfully!</h1>
            <p>Your phone agent is now connected to QuickBooks Online.</p>
            <p><strong>Realm ID:</strong> {realm_id}</p>
            <p><strong>Environment:</strong> {Config.QUICKBOOKS_ENVIRONMENT}</p>
            <hr>
            <p><strong>Next Steps:</strong></p>
            <ol>
                <li>Restart your phone agent server to load new credentials</li>
                <li>Test the connection at <a href="/qb-status">/qb-status</a></li>
                <li>Make sure DETERGENT_PRODUCT_NAME in .env matches your QuickBooks product name</li>
            </ol>
            <p style="color: #666; font-size: 14px; margin-top: 40px;">
                Credentials saved to .env file. Keep this file secure.
            </p>
        </body>
        </html>
        '''

    except Exception as e:
        import traceback
        return f'''
        <html>
        <body style="font-family: Arial; padding: 40px;">
            <h1>Error Completing OAuth</h1>
            <p style="color: red;">{str(e)}</p>
            <pre style="background: #f5f5f5; padding: 10px; overflow-x: auto;">{traceback.format_exc()}</pre>
            <p><a href="/qb-connect">Try again</a></p>
        </body>
        </html>
        ''', 500


@app.route("/qb-status")
def qb_status():
    """Check QuickBooks connection status"""
    try:
        if not Config.QUICKBOOKS_REFRESH_TOKEN:
            return '''
            <html>
            <body style="font-family: Arial; padding: 40px;">
                <h1>QuickBooks Not Connected</h1>
                <p>Your phone agent is not connected to QuickBooks Online.</p>
                <p><a href="/qb-connect" style="display: inline-block; padding: 15px 30px; background: #2ca01c; color: white; text-decoration: none; border-radius: 5px;">Connect Now</a></p>
            </body>
            </html>
            '''

        # Try to get company info to verify connection
        from quickbooks_client import QuickBooksClient
        qb = QuickBooksClient()
        company_name = qb.get_company_info()

        return f'''
        <html>
        <body style="font-family: Arial; padding: 40px;">
            <h1 style="color: #2ca01c;">QuickBooks Connected ✅</h1>
            <p><strong>Company:</strong> {company_name}</p>
            <p><strong>Realm ID:</strong> {Config.QUICKBOOKS_REALM_ID}</p>
            <p><strong>Environment:</strong> {Config.QUICKBOOKS_ENVIRONMENT}</p>
            <p><strong>Product Name:</strong> {Config.DETERGENT_PRODUCT_NAME}</p>
            <hr>
            <p><a href="/orders">View Orders</a> | <a href="/qb-connect">Reconnect</a></p>
        </body>
        </html>
        '''

    except Exception as e:
        import traceback
        return f'''
        <html>
        <body style="font-family: Arial; padding: 40px;">
            <h1>QuickBooks Connection Error ❌</h1>
            <p style="color: red;">Error: {str(e)}</p>
            <pre style="background: #f5f5f5; padding: 10px; overflow-x: auto;">{traceback.format_exc()}</pre>
            <p><a href="/qb-connect">Reconnect</a></p>
        </body>
        </html>
        ''', 500


@app.route("/orders")
def orders_dashboard():
    """View recent orders and sync status"""
    try:
        from database import get_recent_orders

        orders = get_recent_orders(limit=50)

        html = '''
        <html>
        <head>
            <title>Detergent Orders</title>
            <style>
                body { font-family: Arial; padding: 20px; }
                table { border-collapse: collapse; width: 100%; margin-top: 20px; }
                th, td { border: 1px solid #ddd; padding: 12px; text-align: left; font-size: 14px; }
                th { background-color: #4CAF50; color: white; position: sticky; top: 0; }
                .synced { background-color: #d4edda; }
                .pending { background-color: #fff3cd; }
                .failed { background-color: #f8d7da; }
                .nav { margin-bottom: 20px; }
                .nav a { margin-right: 15px; color: #2ca01c; text-decoration: none; }
                .nav a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <h1>Detergent Orders</h1>
            <div class="nav">
                <a href="/qb-status">QuickBooks Status</a> |
                <a href="/orders">Refresh</a>
            </div>
        '''

        if not orders:
            html += '<p>No orders yet. Orders will appear here after customers complete the detergent order flow.</p>'
        else:
            html += f'''
            <p>Showing {len(orders)} most recent orders</p>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Date</th>
                    <th>Name</th>
                    <th>Phone</th>
                    <th>Address</th>
                    <th>Payment</th>
                    <th>Status</th>
                    <th>QBO Invoice</th>
                </tr>
            '''

            for order in orders:
                status_class = order.sync_status
                qb_invoice = order.qb_invoice_number if order.qb_invoice_number else '-'
                date_str = order.created_at.strftime('%Y-%m-%d %H:%M')
                address_short = f"{order.address_city}, {order.address_state}"

                html += f'''
                <tr class="{status_class}">
                    <td>{order.id}</td>
                    <td>{date_str}</td>
                    <td>{order.customer_name}</td>
                    <td>{order.customer_phone}</td>
                    <td>{address_short}</td>
                    <td>{order.payment_method}</td>
                    <td><strong>{order.sync_status}</strong></td>
                    <td>{qb_invoice}</td>
                </tr>
                '''

            html += '</table>'

        html += '''
        </body>
        </html>
        '''

        return html

    except Exception as e:
        import traceback
        return f'''
        <html>
        <body style="font-family: Arial; padding: 40px;">
            <h1>Error Loading Orders</h1>
            <p style="color: red;">Error: {str(e)}</p>
            <pre style="background: #f5f5f5; padding: 10px; overflow-x: auto;">{traceback.format_exc()}</pre>
            <p>Make sure the database is initialized. Run: <code>python database.py</code></p>
        </body>
        </html>
        ''', 500


if __name__ == "__main__":
    print("\n" + "="*80)
    print("PHONE AGENT SERVER STARTING")
    print("="*80)
    print(f"Port: {Config.PORT}")
    print(f"WebSocket URL: {Config.WEBSOCKET_URL}")
    print("="*80 + "\n")

    # Generate greeting audio file with ElevenLabs
    print("Generating greeting audio...")
    greeting_path = generate_greeting_audio()
    if greeting_path:
        print(f"[OK] Greeting audio ready\n")
    else:
        print(f"[WARNING] Greeting audio generation failed - will use Twilio TTS fallback\n")

    # Load or generate cached responses for common questions
    print("="*80)
    cached_loaded = load_cached_responses_from_disk()
    if not cached_loaded:
        print("[Cache] No cache found - generating fresh responses...")
        generate_cached_responses()
    else:
        print("[Cache] [OK] All responses loaded from disk - instant startup!\n")
    print("="*80 + "\n")

    if cached_responses:
        print(f"[READY] Server ready - all optimizations active! ({len(cached_responses)} cached responses)\n")
    else:
        print(f"[WARNING] Server ready - but cache failed. Responses will be SLOW.\n")

    from werkzeug.serving import run_simple
    run_simple('0.0.0.0', Config.PORT, app, use_reloader=False, threaded=True)
