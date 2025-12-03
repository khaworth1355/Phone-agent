# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Phone Agent is an AI-powered call handler that receives phone calls via Twilio, transcribes conversations in real-time using Deepgram, and saves structured transcripts. The system is built to later integrate with Anthropic Claude for AI agent functionality and ElevenLabs for text-to-speech responses.

## Technology Stack

- **Flask** (Web Framework) + **flask-sock** (WebSocket support)
- **Twilio** (Telephony / Call handling)
- **Deepgram SDK 2.12.0** (Real-time speech-to-text transcription)
- **SQLite** (Database - planned)
- **Anthropic Claude** (AI Agent - planned)
- **ElevenLabs** (Text-to-Speech - planned)

## Development Commands

### Running the Application
```bash
python app.py
```
This starts the Flask server on port 5000 with WebSocket support enabled.

### Installing Dependencies
```bash
pip install -r requirements.txt
```

### Environment Setup
Copy `.env.example` to `.env` and configure:
- `TWILIO_ACCOUNT_SID` - Twilio account identifier
- `TWILIO_AUTH_TOKEN` - Twilio authentication token
- `TWILIO_PHONE_NUMBER` - Your Twilio phone number
- `DEEPGRAM_API_KEY` - Deepgram API key for transcription

## Architecture Overview

### Call Flow Architecture

1. **Incoming Call** → `/voice` endpoint receives HTTP request from Twilio
2. **WebSocket Stream** → Twilio opens WebSocket connection to `/media` endpoint
3. **Audio Pipeline** → Audio flows: Twilio → WebSocket → Queue → Deepgram → Transcript
4. **Transcript Storage** → Final transcripts saved to `transcripts/{call_sid}.txt`

### Key Components

**app.py** - Main Flask application
- Routes: `/` (health), `/voice` (call handling), `/media` (WebSocket), `/status` (callbacks)
- Manages WebSocket connections using flask-sock
- Coordinates audio streaming pipeline with threading and asyncio
- Important: Hard-coded cloudflare tunnel URL at line 278 - update for deployment

**call_manager.py** - Call state management (singleton pattern)
- Tracks active calls with metadata (call_sid, caller_number, timestamps)
- Maintains transcript buffers (interim + final results)
- Saves complete transcripts to `transcripts/` directory on call end
- Global instance: `call_manager`

**deepgram_client.py** - Speech-to-text integration
- Uses Deepgram SDK 2.12.0 (older stable version)
- Configured for: mulaw encoding, 8000 Hz sample rate, 1 channel (Twilio format)
- Callback-based architecture: passes transcripts to `on_transcript_callback(text, is_final)`
- Handles both interim and final transcription results

**websocket_handler.py** - Alternative WebSocket implementation (not currently in use)
- Contains SocketIO-based handlers
- Current implementation uses flask-sock directly in app.py instead

**config.py** - Configuration loader
- Loads environment variables via python-dotenv
- Flask config: DEBUG=True, PORT=5000

### Audio Processing Pipeline

The system uses a multi-threaded architecture to handle real-time audio:

1. **Main Thread**: Flask server handles HTTP/WebSocket connections
2. **WebSocket Handler**: Receives audio from Twilio, decodes base64, adds to queue
3. **Deepgram Worker Thread**:
   - Runs async event loop
   - Maintains persistent Deepgram WebSocket connection
   - Pulls audio from queue and sends to Deepgram
   - Processes transcript callbacks

Audio format: mulaw encoded, 8kHz, mono (Twilio's default format for phone calls)

### Session Management

- `active_transcribers` dict: Maps session_id → {transcriber, call_sid, stream_sid, audio_queue, running, connected}
- `transcriber_locks` dict: Prevents duplicate initialization
- Cleanup happens on stream stop or WebSocket disconnect

### Transcript Format

Transcripts saved to `transcripts/{call_sid}.txt` include:
- Call metadata (SID, caller number, timestamps, duration)
- Full transcript (final results only)
- Detailed transcript (all interim + final with timestamps)

## Important Notes

- **Deepgram SDK Version**: Uses 2.12.0 (older stable version) - event handler syntax differs from newer versions
- **WebSocket URL**: Currently hard-coded in app.py:278 - must update for different environments
- **Threading Model**: Combines Flask threading with asyncio event loops - be careful with blocking operations
- **Queue Size**: Audio queue limited to 100 items - drops audio if full (non-blocking)
- **Transcript Directory**: `transcripts/` folder must exist or creation will fail

## Current Development Status

- [x] Basic call receiving
- [x] Speech-to-text integration (Deepgram)
- [x] Transcript capture and storage
- [ ] AI agent integration (Claude)
- [ ] Text-to-speech integration (ElevenLabs)
- [ ] Database persistence (SQLite)
- [ ] Structured note-taking system