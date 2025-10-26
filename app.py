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

    # Re-establish media stream (inbound only to prevent echo)
    start = Start()
    stream = start.stream(url=Config.WEBSOCKET_URL)
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

        # Get Claude's response
        print(f"[AI] Calling Claude...")
        ai_text = await claude.get_response(user_text)
        print(f"[AI] Claude responded: '{ai_text}'\n")

        # Convert to speech
        print(f"[AI] Generating speech...")
        audio_bytes = await tts.text_to_speech(ai_text)

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
        conv_mgr.finish_ai_response(ai_text)

        # Log AI response to call manager (as final transcript)
        call_manager.add_transcript(call_sid, ai_text, is_final=True, speaker='AI')

    except Exception as e:
        print(f"[AI] ❌ Error: {e}")
        import traceback
        traceback.print_exc()


def deepgram_worker(session_id, call_sid):
    """Worker thread for Deepgram connection and conversation management"""

    if session_id not in sessions:
        return

    conv_mgr = sessions[session_id]['conversation_manager']

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
                        # Trigger AI response
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

    from werkzeug.serving import run_simple
    run_simple('0.0.0.0', Config.PORT, app, use_reloader=False, threaded=True)
