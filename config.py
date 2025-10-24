import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

    DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')

    # WebSocket URL - Update this for your environment
    WEBSOCKET_URL = os.getenv('WEBSOCKET_URL', 'wss://recommendations-editing-seas-plug.trycloudflare.com/media')

    # Flask config
    DEBUG = True
    PORT = 5000
