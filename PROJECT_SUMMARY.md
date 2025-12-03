# Project Summary: AI Phone Agent

## What We Built
A fully functional AI phone agent that:
- Receives calls via Twilio
- Transcribes speech in real-time using Deepgram
- Detects conversation pauses (2s threshold)
- Responds intelligently using Claude AI (Haiku)
- Maintains conversation history
- Supports barge-in interruption

## Current Status

### ✅ Working
- **Call Handling**: Twilio + Cloudflare tunnel (wss://hitachi-optical-bond-eagle.trycloudflare.com/media)
- **Speech-to-Text**: Deepgram SDK 2.12.0 with mulaw, 8kHz, mono
- **Pause Detection**: ConversationManager detects 2-second silence
- **AI Responses**: Claude 3 Haiku (claude-3-haiku-20240307)
- **Conversation Memory**: Full history tracking
- **Transcription Storage**: Saves to `transcripts/` with timestamp filenames

### ❌ Not Working
- **Text-to-Speech**: ElevenLabs integration blocked by Python 3.14 compatibility issue (missing `audioop` module)
- Claude's responses are generated but caller can't hear them

## Tech Stack
- Python 3.14 (causing TTS issues)
- Flask + flask-sock (WebSocket)
- Twilio (telephony)
- Deepgram SDK 2.12.0 (STT)
- Anthropic Claude API (AI)
- ElevenLabs API (TTS - not functional)

## Key Files
- `app.py`: Main Flask app with WebSocket handling
- `conversation_manager.py`: Pause detection & state management
- `claude_client.py`: Claude API integration (async)
- `elevenlabs_client.py`: TTS client (broken due to audioop)
- `deepgram_client.py`: Speech-to-text client
- `call_manager.py`: Call state and transcript logging
- `config.py`: Configuration (API keys, models, timeouts)

## API Keys (Configured)
- Twilio: ✓
- Deepgram: ✓
- Anthropic: ✓ (works with Haiku only)
- ElevenLabs: ✓ (can't use due to Python 3.14)

## Known Issues
1. **Python 3.14 + pydub**: `audioop` module removed, breaks audio conversion for TTS
2. **Claude Model Access**: Only Haiku model available with current API key (Sonnet returns 404 errors)
3. **Async event loop warning**: Deepgram task cleanup issue (non-critical)
4. **ffmpeg**: Not installed, needed for pydub audio processing

## Architecture
```
Caller → Twilio → Cloudflare Tunnel → Flask WebSocket → Deepgram STT
                                                            ↓
                                                    Conversation Manager
                                                            ↓
                                                       Pause Detection
                                                            ↓
                                                        Claude AI
                                                            ↓
                                                    [ElevenLabs TTS] ❌
                                                            ↓
                                                    [Back to Caller] ❌
```

## Test Results
Last successful test showed:
- User: "Hello. Can you hear me?"
- Claude: "Yes, I can hear you loud and clear. How may I assist you today?"
- Response time: ~2s after pause detection
- Conversation history tracking works
- Transcription saved successfully

## Configuration Details

### Pause Detection
- Threshold: 2.0 seconds (configurable in `config.py`)
- Detects both final transcripts and silence periods
- Triggers AI response automatically

### Claude Settings
- Model: claude-3-haiku-20240307
- Max tokens: 200
- Timeout: 15 seconds
- System prompt: Optimized for phone conversations (concise responses)

### Deepgram Settings
- Model: nova-2
- Language: en-US
- Encoding: mulaw, 8kHz, mono (Twilio format)
- Interim results: Enabled
- Punctuation: Enabled

## Environment Variables Required
```
TWILIO_ACCOUNT_SID=<configured>
TWILIO_AUTH_TOKEN=<configured>
TWILIO_PHONE_NUMBER=<configured>
DEEPGRAM_API_KEY=<configured>
ANTHROPIC_API_KEY=<configured>
ELEVENLABS_API_KEY=<configured>
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM (Rachel)
WEBSOCKET_URL=<updated per tunnel session>
```

## Project Location
`C:\Users\khawo\PycharmProjects\Phone-agent\`

## Next Steps to Consider
1. **Fix TTS** - Options:
   - Downgrade to Python 3.11/3.12
   - Find alternative audio library
   - Use Twilio's built-in TTS as fallback

2. **Features to Add**:
   - Database persistence for conversations
   - Multi-turn conversation improvements
   - Custom system prompts for different use cases
   - Better error handling and fallbacks
   - Conversation analytics

3. **Production Readiness**:
   - Deploy to production server
   - Use persistent tunnel (not Cloudflare temporary)
   - Add monitoring and logging
   - Implement rate limiting
   - Add authentication for admin features

## Development Commands
```bash
# Run the application
python app.py

# Start Cloudflare tunnel (in separate terminal)
cloudflared tunnel --url http://localhost:5000

# Install dependencies
pip install -r requirements.txt

# Note: Update WEBSOCKET_URL in .env with new tunnel URL each session
```

## Recent Changes
- Switched from Claude 3.5 Sonnet to Claude 3 Haiku (API compatibility)
- Added comprehensive logging throughout pipeline
- Implemented conversation state management
- Added pause detection with configurable threshold
- Created modular architecture with separate client files
- Added barge-in detection (not fully tested yet)
