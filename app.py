"""
Main Flask Application - Simplified with proper Deepgram integration
"""
from flask import Flask, request
from flask_sock import Sock
from twilio.twiml.voice_response import VoiceResponse, Start
from config import Config
from call_manager import call_manager
import json
import base64
import asyncio
import threading
import queue
from deepgram_client import DeepgramTranscriber

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Initialize WebSocket
sock = Sock(app)

print("[App] Flask-Sock initialized")

# Store active transcribers
active_transcribers = {}
transcriber_locks = {}


@sock.route('/media')
def media_websocket(ws):
    """Handle WebSocket connection for Twilio Media Stream"""
    session_id = id(ws)

    print(f"\n{'='*60}")
    print(f"[WebSocket] CLIENT CONNECTED!")
    print(f"{'='*60}")
    print(f"[WebSocket] Session ID: {session_id}")
    print(f"{'='*60}\n")

    try:
        while True:
            message = ws.receive()
            if message is None:
                break

            try:
                data = json.loads(message)
                event_type = data.get('event')

                if event_type == 'connected':
                    print(f"[WebSocket] Twilio connected")
                elif event_type == 'start':
                    print(f"[WebSocket] Received event: start")
                    handle_stream_start(data, session_id)
                elif event_type == 'media':
                    handle_media_data(data, session_id)
                elif event_type == 'stop':
                    print(f"[WebSocket] Received event: stop")
                    handle_stream_stop(data, session_id)
                    break

            except json.JSONDecodeError as e:
                print(f"[WebSocket] JSON decode error: {e}")
            except Exception as e:
                print(f"[WebSocket] Error processing message: {e}")
                import traceback
                traceback.print_exc()

    except Exception as e:
        print(f"[WebSocket] Connection error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"\n[WebSocket] Client disconnected: {session_id}")
        cleanup_session(session_id)


def handle_stream_start(data, session_id):
    """Handle start of media stream"""
    # Prevent duplicate initialization
    if session_id in transcriber_locks:
        print(f"[WebSocket] Session {session_id} already initialized, skipping")
        return

    transcriber_locks[session_id] = True

    stream_sid = data['streamSid']
    call_sid = data['start']['callSid']

    print(f"\n{'='*60}")
    print(f"[WebSocket] STREAM STARTED")
    print(f"{'='*60}")
    print(f"[WebSocket] Stream SID: {stream_sid}")
    print(f"[WebSocket] Call SID: {call_sid}")
    print(f"{'='*60}\n")

    call_manager.set_stream_sid(call_sid, stream_sid)

    def on_transcript(text, is_final):
        """Callback for when transcripts are received"""
        print(f"[Transcript Callback] Received: is_final={is_final}, text='{text}'")
        call_manager.add_transcript(call_sid, text, is_final)

    print(f"[Deepgram] Creating transcriber...")
    transcriber = DeepgramTranscriber(on_transcript_callback=on_transcript)

    # Create audio queue
    audio_queue = queue.Queue(maxsize=100)

    active_transcribers[session_id] = {
        'transcriber': transcriber,
        'call_sid': call_sid,
        'stream_sid': stream_sid,
        'audio_queue': audio_queue,
        'running': True,
        'connected': False
    }

    print(f"[Deepgram] Starting connection...")

    def deepgram_worker():
        """Background worker for Deepgram connection"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def run():
            try:
                # Connect
                print("[Deepgram] Attempting to connect...")
                connected = await transcriber.connect()

                if not connected:
                    print("[Deepgram] ❌ Connection failed!")
                    return

                print("[Deepgram] ✅ Connected successfully!")
                active_transcribers[session_id]['connected'] = True

                # Process audio queue
                audio_count = 0
                while active_transcribers.get(session_id, {}).get('running', False):
                    try:
                        audio_data = audio_queue.get(timeout=0.1)
                        if audio_data:
                            await transcriber.send_audio(audio_data)
                            audio_count += 1
                            if audio_count % 50 == 0:
                                print(f"[Deepgram] Sent {audio_count} audio chunks")
                    except queue.Empty:
                        await asyncio.sleep(0.01)
                    except Exception as e:
                        print(f"[Deepgram] Error sending audio: {e}")

                # Cleanup
                print(f"[Deepgram] Closing connection (processed {audio_count} audio chunks)")
                await transcriber.close()

            except Exception as e:
                print(f"[Deepgram] Worker exception: {e}")
                import traceback
                traceback.print_exc()

        loop.run_until_complete(run())

    worker = threading.Thread(target=deepgram_worker, daemon=True)
    worker.start()

    # Wait for connection
    import time
    for i in range(10):  # Wait up to 5 seconds
        if active_transcribers.get(session_id, {}).get('connected'):
            print(f"[Deepgram] Ready to receive audio!")
            break
        time.sleep(0.5)
    else:
        print(f"[Deepgram] ⚠️ Connection timeout - may not be ready")


def handle_media_data(data, session_id):
    """Handle incoming audio data"""
    if session_id not in active_transcribers:
        return

    transcriber_data = active_transcribers[session_id]

    if not transcriber_data.get('connected'):
        return

    audio_queue = transcriber_data.get('audio_queue')
    if not audio_queue:
        return

    try:
        payload = data['media']['payload']
        audio_bytes = base64.b64decode(payload)

        # Add to queue (non-blocking)
        try:
            audio_queue.put_nowait(audio_bytes)
        except queue.Full:
            pass  # Skip if queue is full

    except Exception as e:
        print(f"[WebSocket] Error handling media: {e}")


def handle_stream_stop(data, session_id):
    """Handle end of media stream"""
    if session_id not in active_transcribers:
        return

    transcriber_data = active_transcribers[session_id]
    call_sid = transcriber_data['call_sid']

    print(f"\n[WebSocket] Stream stopped for call {call_sid}")

    # Stop the worker
    transcriber_data['running'] = False

    # Wait for processing to finish
    import time
    time.sleep(2)

    final_transcript = call_manager.get_full_transcript(call_sid, final_only=True)

    print(f"\n{'=' * 60}")
    print(f"FINAL TRANSCRIPT FOR CALL {call_sid}:")
    print(f"{'=' * 60}")
    print(final_transcript if final_transcript else "(No transcript recorded)")
    print(f"{'=' * 60}\n")

    cleanup_session(session_id)


def cleanup_session(session_id):
    """Clean up session data"""
    if session_id in active_transcribers:
        transcriber_data = active_transcribers[session_id]
        call_sid = transcriber_data['call_sid']
        del active_transcribers[session_id]
        call_manager.end_call(call_sid)

    if session_id in transcriber_locks:
        del transcriber_locks[session_id]


@app.route("/")
def home():
    """Home route"""
    return "Phone Agent Server is Running! (Day 2: STT Enabled)", 200


@app.route("/voice", methods=['GET', 'POST'])
def voice():
    """Handle incoming voice calls"""
    caller_number = request.values.get('From', 'Unknown')
    call_sid = request.values.get('CallSid', 'Unknown')

    print(f"\n{'='*60}")
    print(f"INCOMING CALL")
    print(f"{'='*60}")
    print(f"From: {caller_number}")
    print(f"Call SID: {call_sid}")
    print(f"{'='*60}\n")

    call_manager.create_call(call_sid, caller_number)

    response = VoiceResponse()

    response.say(
        "Hello! Please speak now and I will transcribe what you say.",
        voice='Polly.Joanna',
        language='en-US'
    )

    start = Start()
    start.stream(url='wss://guy-cooked-illustrations-lake.trycloudflare.com/media')
    response.append(start)

    response.pause(length=60)

    response.say("Goodbye!", voice='Polly.Joanna')

    return str(response), 200, {'Content-Type': 'text/xml'}


@app.route("/status", methods=['POST'])
def status():
    """Handle call status callbacks"""
    call_status = request.values.get('CallStatus', 'Unknown')
    call_sid = request.values.get('CallSid', 'Unknown')

    print(f"\n[Status] Call {call_sid}: {call_status}")

    return "", 200


print("[App] All routes registered")

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"🚀 STARTING PHONE AGENT SERVER")
    print(f"{'='*60}")
    print(f"📞 HTTP: http://localhost:{Config.PORT}")
    print(f"🔌 WebSocket: ws://localhost:{Config.PORT}/media")
    print(f"🎤 STT: Deepgram Enabled")
    print(f"{'='*60}\n")

    from werkzeug.serving import run_simple

    run_simple(
        '0.0.0.0',
        Config.PORT,
        app,
        use_reloader=False,
        use_debugger=False,
        threaded=True
    )
