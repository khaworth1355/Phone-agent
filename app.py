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
            'keywords': ['owner', 'who owns', 'mark'],
            'response': "The owner of TEMCO is Mark Hayworth."
        },
        'contact': {
            'keywords': ['phone', 'number', 'contact', 'reach', 'call'],
            'response': "You can reach TEMCO at 800-245-1869."
        }
    }

    try:
        # Create temporary ElevenLabs client
        tts = ElevenLabsClient()

        # Generate audio for each response
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

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
                    print(f"[Cache] ✅ Cached: {key}")
                else:
                    print(f"[Cache] ⚠️  Failed: {key}")

            except Exception as e:
                print(f"[Cache] Error caching {key}: {e}")

        loop.close()

        print(f"[Cache] ✅ Cached {len(cached_responses)} responses\n")
        return True

    except Exception as e:
        print(f"[Cache] ❌ Error generating cached responses: {e}")
        return False


def check_cached_response(user_text):
    """
    Check if user's question matches a cached response

    Args:
        user_text: User's spoken text

    Returns:
        dict with 'audio' and 'text' if match found, None otherwise
    """
    if not user_text or not cached_responses:
        return None

    text_lower = user_text.lower()

    # Check each cached response
    for key, cached in cached_responses.items():
        # Count keyword matches
        matches = sum(1 for keyword in cached['keywords'] if keyword in text_lower)

        # If multiple keywords match, likely a match
        if matches >= 2:
            print(f"[Cache] 🎯 Match found: {key}")
            return {
                'audio': cached['audio'],
                'text': cached['response'],
                'transfer': False
            }

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
            message = json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": payload
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
            print(f"[Transfer Detection] 🎯 Keyword match: '{keyword}'")
            return True

    # Check for buying intent
    for keyword in buying_keywords:
        if keyword in text_lower:
            print(f"[Transfer Detection] 🎯 Buying intent: '{keyword}'")
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

        # FALLBACK: Check for transfer intent via keywords (safety net if Claude doesn't trigger)
        keyword_transfer_detected = detect_transfer_intent(user_text)
        if keyword_transfer_detected:
            print(f"[AI] 🚨 Fallback transfer detection activated!")

        # Get Claude's response
        print(f"[AI] Calling Claude...")
        ai_text = await claude.get_response(user_text)
        print(f"[AI] Claude responded: '{ai_text}'\n")

        # Check for transfer request from Claude
        transfer_requested_by_claude = '[TRANSFER_TO_SALES]' in ai_text

        # Combine Claude's decision with keyword fallback
        transfer_requested = transfer_requested_by_claude or keyword_transfer_detected

        # Remove transfer marker from spoken text
        spoken_text = ai_text.replace('[TRANSFER_TO_SALES]', '').strip()

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

                # Check for transfer
                transfer_requested = '[TRANSFER_TO_SALES]' in ai_text
                spoken_text = ai_text.replace('[TRANSFER_TO_SALES]', '').strip()

                # Generate audio
                audio_bytes = await tts.text_to_speech(spoken_text)

                if audio_bytes:
                    predictive_response_data['result'] = {
                        'audio': audio_bytes,
                        'text': spoken_text,
                        'transfer': transfer_requested,
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

                    # Yield to event loop to process sends
                    await asyncio.sleep(0)

                except Empty:
                    await asyncio.sleep(0.01)

                # Check for pause detection every 0.5 seconds
                current_time = time.time()
                if current_time - last_pause_check >= 0.5:
                    last_pause_check = current_time

                    # Check if user has paused speaking
                    if conv_mgr.check_for_pause():
                        user_text = conv_mgr.get_user_text()

                        # PRIORITY 1: Check cached responses (instant)
                        cached_result = check_cached_response(user_text)
                        if cached_result:
                            print(f"[Conversation] 💨 Using cached response!")
                            conv_mgr.start_ai_response()
                            send_audio_to_twilio(call_sid, cached_result['audio'])
                            conv_mgr.finish_ai_response(cached_result['text'])
                            call_manager.add_transcript(call_sid, cached_result['text'], is_final=True, speaker='AI')

                            # Clear predictive response if any
                            predictive_response_data['result'] = None

                        # PRIORITY 2: Check if predictive response is ready
                        elif predictive_response_data['result']:
                            print(f"[Conversation] ⚡ Using pre-generated response!")
                            result = predictive_response_data['result']

                            # Play the pre-generated audio
                            conv_mgr.start_ai_response()
                            send_audio_to_twilio(call_sid, result['audio'])
                            conv_mgr.finish_ai_response(result['text'])
                            call_manager.add_transcript(call_sid, result['text'], is_final=True, speaker='AI')

                            # Handle transfer if needed
                            if result['transfer']:
                                await asyncio.sleep(2)
                                transfer_call(call_sid, Config.SALES_FORWARD_NUMBER)

                            # Clear predictive response
                            predictive_response_data['result'] = None

                        else:
                            # No predictive response ready, generate normally
                            print(f"[Conversation] Triggering AI response...")
                            await handle_ai_response(session_id)

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
        print(f"✅ Greeting audio ready\n")
    else:
        print(f"⚠️ Greeting audio generation failed - will use Twilio TTS fallback\n")

    # Generate cached responses for common questions
    print("="*80)
    generate_cached_responses()
    print("="*80 + "\n")

    print("🚀 Server ready - all optimizations active!\n")

    from werkzeug.serving import run_simple
    run_simple('0.0.0.0', Config.PORT, app, use_reloader=False, threaded=True)
