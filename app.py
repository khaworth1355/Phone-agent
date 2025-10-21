"""
Main Flask Application
Handles HTTP routes and initializes WebSocket server
"""
# Patch for async support
import eventlet
eventlet.monkey_patch()

from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Start
from config import Config
from call_manager import call_manager
from websocket_handler import init_socketio





# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Initialize SocketIO
socketio = init_socketio(app)


@app.route("/")
def home():
    """Home route to verify server is running"""
    return "Phone Agent Server is Running! (Day 2: STT Enabled)", 200


@app.route("/voice", methods=['GET', 'POST'])
def voice():
    """Handle incoming voice calls from Twilio"""
    # Get caller information
    caller_number = request.values.get('From', 'Unknown')
    call_sid = request.values.get('CallSid', 'Unknown')

    print(f"\n{'=' * 60}")
    print(f"INCOMING CALL")
    print(f"{'=' * 60}")
    print(f"From: {caller_number}")
    print(f"Call SID: {call_sid}")
    print(f"{'=' * 60}\n")

    # Create call record in call manager
    call_manager.create_call(call_sid, caller_number)

    # Create TwiML response
    response = VoiceResponse()

    # Add greeting
    response.say(
        "Hello! I am your A I assistant. I will transcribe everything you say. "
        "Please tell me how I can help you today.",
        voice='Polly.Joanna',
        language='en-US'
    )

    # Start media stream to WebSocket
    # IMPORTANT: Replace YOUR_NGROK_URL with your actual ngrok URL
    start = Start()
    start.stream(url=f'wss://abc123def456.ngrok.io/media')
