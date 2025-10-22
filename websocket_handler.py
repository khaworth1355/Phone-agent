"""
WebSocket Handler Module
Manages WebSocket connections for Twilio Media Streams
"""
import asyncio
import base64
import json
from flask import request
from deepgram_client import DeepgramTranscriber
from call_manager import call_manager

# Store active Deepgram connections per WebSocket session
active_transcribers = {}


def register_websocket_handlers(socketio_instance):
    """
    Register WebSocket event handlers

    Args:
        socketio_instance: The SocketIO instance to register handlers with
    """

    @socketio_instance.on('connect', namespace='/media')
    def handle_connect():
        """Handle WebSocket connection from Twilio"""
        print(f"\n{'='*60}")
        print(f"[WebSocket] CLIENT CONNECTED!")
        print(f"{'='*60}")
        print(f"[WebSocket] Session ID: {request.sid}")
        print(f"{'='*60}\n")

    @socketio_instance.on('message', namespace='/media')
    def handle_message(message):
        """
        Handle incoming messages from Twilio Media Stream

        Args:
            message: JSON message from Twilio
        """
        try:
            data = json.loads(message) if isinstance(message, str) else message
            event_type = data.get('event')

            print(f"[WebSocket] Received event: {event_type}")

            if event_type == 'start':
                handle_stream_start(data, request.sid)
            elif event_type == 'media':
                handle_media_data(data, request.sid)
            elif event_type == 'stop':
                handle_stream_stop(data, request.sid)

        except json.JSONDecodeError as e:
            print(f"[WebSocket] JSON decode error: {e}")
        except Exception as e:
            print(f"[WebSocket] Error handling message: {e}")
            import traceback
            traceback.print_exc()

    @socketio_instance.on('disconnect', namespace='/media')
    def handle_disconnect():
        """Handle WebSocket disconnection"""
        print(f"\n[WebSocket] Client disconnected: {request.sid}")

        # Clean up if transcriber exists
        if request.sid in active_transcribers:
            transcriber_data = active_transcribers[request.sid]
            transcriber = transcriber_data['transcriber']
            asyncio.create_task(transcriber.close())
            del active_transcribers[request.sid]

    print("[WebSocket] Event handlers registered for /media namespace")


def handle_stream_start(data, session_id):
    """
    Handle start of media stream

    Args:
        data: Start event data from Twilio
        session_id: WebSocket session ID
    """
    stream_sid = data['streamSid']
    call_sid = data['start']['callSid']

    print(f"\n{'='*60}")
    print(f"[WebSocket] STREAM STARTED")
    print(f"{'='*60}")
    print(f"[WebSocket] Stream SID: {stream_sid}")
    print(f"[WebSocket] Call SID: {call_sid}")
    print(f"{'='*60}\n")

    # Update call manager with stream SID
    call_manager.set_stream_sid(call_sid, stream_sid)

    # Create transcript callback for this call
    def on_transcript(text, is_final):
        call_manager.add_transcript(call_sid, text, is_final)

    # Create and connect Deepgram transcriber
    transcriber = DeepgramTranscriber(on_transcript_callback=on_transcript)

    # Store transcriber
    active_transcribers[session_id] = {
        'transcriber': transcriber,
        'call_sid': call_sid,
        'stream_sid': stream_sid
    }

    # Connect to Deepgram (async)
    asyncio.create_task(transcriber.connect())

    print(f"[WebSocket] Deepgram transcriber created for session {session_id}")


def handle_media_data(data, session_id):
    """
    Handle incoming audio data from Twilio

    Args:
        data: Media event data containing audio
        session_id: WebSocket session ID
    """
    if session_id not in active_transcribers:
        return

    transcriber_data = active_transcribers[session_id]
    transcriber = transcriber_data['transcriber']

    # Extract and decode audio
    payload = data['media']['payload']
    audio_bytes = base64.b64decode(payload)

    # Send to Deepgram (async)
    if transcriber.is_connected:
        asyncio.create_task(transcriber.send_audio(audio_bytes))


def handle_stream_stop(data, session_id):
    """
    Handle end of media stream

    Args:
        data: Stop event data from Twilio
        session_id: WebSocket session ID
    """
    if session_id not in active_transcribers:
        return

    transcriber_data = active_transcribers[session_id]
    call_sid = transcriber_data['call_sid']
    transcriber = transcriber_data['transcriber']

    print(f"\n[WebSocket] Stream stopped for call {call_sid}")

    # Close Deepgram connection
    asyncio.create_task(transcriber.close())

    # Get final transcript
    final_transcript = call_manager.get_full_transcript(call_sid, final_only=True)

    print(f"\n{'=' * 60}")
    print(f"FINAL TRANSCRIPT FOR CALL {call_sid}:")
    print(f"{'=' * 60}")
    print(final_transcript)
    print(f"{'=' * 60}\n")

    # Clean up
    del active_transcribers[session_id]
    call_manager.end_call(call_sid)


