from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse
from config import Config

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)


@app.route("/")
def home():
    """Home route to verify server is running"""
    return "Phone Agent Server is Running!", 200


@app.route("/voice", methods=['GET', 'POST'])
def voice():
    """Handle incoming voice calls from Twilio"""
    # Log ALL request data for debugging
    print(f"\n{'=' * 50}")
    print(f"Incoming Call - Full Details:")
    print(f"{'=' * 50}")

    # Common Twilio parameters
    print(f"From: {request.values.get('From', 'N/A')}")
    print(f"To: {request.values.get('To', 'N/A')}")
    print(f"Call SID: {request.values.get('CallSid', 'N/A')}")
    print(f"Call Status: {request.values.get('CallStatus', 'N/A')}")
    print(f"Direction: {request.values.get('Direction', 'N/A')}")
    print(f"From City: {request.values.get('FromCity', 'N/A')}")
    print(f"From State: {request.values.get('FromState', 'N/A')}")
    print(f"From Country: {request.values.get('FromCountry', 'N/A')}")

    # Print all parameters
    print(f"\nAll Parameters:")
    for key, value in request.values.items():
        print(f"  {key}: {value}")
    print(f"{'=' * 50}\n")

    # Create TwiML response
    response = VoiceResponse()
    response.say(
        "Hello! This is your A I phone agent. This is a test call. Thank you for calling!",
        voice='Polly.Joanna',
        language='en-US'
    )
    response.pause(length=1)
    response.say("Goodbye!", voice='Polly.Joanna', language='en-US')

    return str(response), 200, {'Content-Type': 'text/xml'}


@app.route("/status", methods=['POST'])
def status():
    """Handle call status callbacks from Twilio"""
    call_status = request.values.get('CallStatus', 'Unknown')
    call_sid = request.values.get('CallSid', 'Unknown')

    print(f"\nCall Status Update:")
    print(f"Call SID: {call_sid}")
    print(f"Status: {call_status}\n")

    return "", 200


if __name__ == "__main__":
    print(f"\n🚀 Starting Phone Agent Server...")
    print(f"📞 Server will run on http://localhost:{Config.PORT}")
    print(f"🔗 Make sure to start ngrok in another terminal!")
    print(f"\nPress CTRL+C to stop the server\n")

    app.run(
        host='0.0.0.0',  # Allow external connections
        port=Config.PORT,
        debug=Config.DEBUG
    )
