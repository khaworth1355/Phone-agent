"""
Configuration Module
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Twilio credentials
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

    # Deepgram API key
    DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')

    # Cloudflare tunnel URL (update this with your current tunnel)
    # Format: wss://your-tunnel.trycloudflare.com/media
    WEBSOCKET_URL = os.getenv('WEBSOCKET_URL', 'wss://anne-cedar-bonds-towers.trycloudflare.com/media')

    # Flask settings
    PORT = 5000
    DEBUG = True
