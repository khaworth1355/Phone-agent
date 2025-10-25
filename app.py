"""
Phone Agent - Twilio + Deepgram Transcription
"""
import sys
import json
import base64
import asyncio
import threading
from queue import Queue, Empty

from flask import Flask, request
from flask_sock import Sock
from twilio.twiml.voice_response import VoiceResponse, Start

from config import Config
from call_manager import call_manager
from deepgram_client import DeepgramClient

# Ensure real-time console output
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

# Initialize Flask
app = Flask(__name__)
sock = Sock(app)

# Store active sessions
sessions = {}


@app.route("/")
def home():
    """Health check"""
    return "Phone Agent Running!", 200


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
    response.say("Hello! Please speak now. I will transcribe what you say.", voice='Polly.Joanna')

    # Start media stream
    start = Start()
    start.stream(url=Config.WEBSOCKET_URL)
    response.append(start)

    response.pause(length=60)
    response.say("Thank you. Goodbye.", voice='Polly.Joanna')

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
                print(f"[Stream Start] Stream: {stream_sid}\n")

                # Create session
                sessions[session_id] = {
                    'call_sid': call_sid,
                    'audio_queue': Queue(),
                    'running': True,
                    'audio_received_count': 0
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
            del sessions[session_id]

        if call_sid:
            call_manager.end_call(call_sid)

        print("[WebSocket] Disconnected\n")


def deepgram_worker(session_id, call_sid):
    """Worker thread for Deepgram connection"""

    def on_transcript(text, is_final):
        """Callback when transcript received"""
        call_manager.add_transcript(call_sid, text, is_final)

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

        # Process audio queue
        audio_count = 0

        while sessions.get(session_id, {}).get('running', False):
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

            except Exception as e:
                print(f"[Deepgram] Error: {e}")
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
