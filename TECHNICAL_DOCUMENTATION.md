# Phone Agent - Technical Architecture Documentation

**Version:** 1.0
**Last Updated:** December 2, 2025
**Author:** Technical Documentation

---

## Executive Summary

Phone Agent is an AI-powered telephony system that handles incoming calls through an intelligent routing workflow. The system receives calls via Twilio, performs real-time speech-to-text transcription using Deepgram, routes callers to appropriate departments using a hybrid keyword/AI routing engine, and provides natural language responses via Anthropic Claude and ElevenLabs text-to-speech.

The architecture emphasizes real-time processing, low-latency responses, and continuous transcription throughout the call lifecycle, even during agent transfers.

---

## System Architecture

### High-Level Architecture

```
[Caller] → [Twilio] → [Flask App] → [Deepgram STT]
                           ↓
                    [Claude AI Agent]
                           ↓
                    [Routing Engine]
                           ↓
               [Conference Bridge + Agent Transfer]
                           ↓
                    [PostgreSQL Database]
                           ↓
                [QuickBooks Online] (for detergent orders)
```

### Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Web Framework** | Flask | Latest | HTTP/WebSocket server |
| **WebSocket** | flask-sock | Latest | Real-time audio streaming |
| **Telephony** | Twilio | API v2010 | Call handling, conferencing |
| **Speech-to-Text** | Deepgram SDK | 2.12.0 | Real-time transcription |
| **AI Agent** | Anthropic Claude | claude-3-haiku | Conversational AI |
| **Text-to-Speech** | ElevenLabs | eleven_turbo_v2_5 | Voice synthesis |
| **Database** | PostgreSQL + SQLAlchemy | Latest | Data persistence |
| **ERP Integration** | QuickBooks Online | OAuth 2.0 | Order/customer management |
| **Language** | Python | 3.x | Core application |

---

## Call Flow Architecture

### Complete Call Lifecycle

1. **Incoming Call** → `/voice` endpoint receives HTTP webhook from Twilio
2. **Greeting & Setup** → TwiML response establishes conference + media stream
3. **Audio Streaming** → Twilio opens WebSocket connection to `/media`
4. **Real-time Transcription** → Audio chunks → Deepgram → Text transcripts
5. **Conversation Flow**:
   - AI greets caller
   - AI asks "How can I help you today?"
   - Routing engine analyzes response
   - AI confirms routing decision
6. **Call Transfer** → Agent dialed into conference bridge
7. **Continuous Transcription** → Media stream stays open, transcription continues
8. **Post-Call Processing** → Transcript saved to database + file system

### Audio Pipeline Threading Model

The system uses a sophisticated multi-threaded architecture:

```
Main Thread: Flask HTTP/WebSocket Server
    ├── WebSocket Handler Thread: Receives Twilio audio chunks
    │   └── Audio Queue (non-blocking, size=100)
    │
    └── Deepgram Worker Thread: Async event loop
        ├── Pulls audio from queue
        ├── Sends to Deepgram WebSocket
        └── Processes transcript callbacks
```

**Audio Format:** mulaw (G.711 μ-law), 8kHz sample rate, mono channel

---

## Core Modules

### 1. **app.py** - Main Application Controller

**Location:** `app.py`
**Lines of Code:** ~1000+
**Purpose:** Central orchestrator for all system components

**Key Responsibilities:**
- Flask application initialization and routing
- WebSocket connection management (flask-sock)
- Call lifecycle coordination
- Real-time audio streaming pipeline
- AI conversation orchestration
- Response caching system
- Conference bridge management

**Critical HTTP Endpoints:**
- `GET /` - Health check
- `POST /voice` - Twilio incoming call webhook (returns TwiML)
- `WebSocket /media` - Real-time audio streaming
- `POST /status` - Call status callbacks
- `POST /conference-status` - Conference event tracking
- `POST /participant-status` - Participant join/leave events

**WebSocket Message Flow:**
```
Twilio → "start" event → Initialize Deepgram connection
Twilio → "media" event → Base64 audio → Decode → Send to Deepgram
Twilio → "stop" event → Close connections, save transcript
```

**Notable Features:**
- Response caching: Pre-generates TTS for common questions at startup
- Cache persistence: Saves to `cached_audio/*.ulaw` files
- Barge-in detection: Stops AI speech when user interrupts
- Predictive responses: Starts generating response on stable interim transcripts
- Structured data collection: Adjustable pause thresholds for phone numbers/addresses

**Configuration Constants:**
- `DETERGENT_WORKFLOW_ENABLED = False` (Feature flag for order collection)
- Audio queue: 100 items max, non-blocking
- Temp directory: `temp_audio/` for streaming audio files

---

### 2. **config.py** - Configuration Management

**Location:** `config.py`
**Lines of Code:** 154
**Purpose:** Centralized configuration and environment management

**Configuration Sources:**
1. Environment variables (`.env` file)
2. `knowledge_base.txt` file (injected into Claude system prompt)
3. Default values with fallbacks

**Key Configuration Sections:**

**Twilio:**
```python
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_PHONE_NUMBER
```

**Deepgram:**
```python
DEEPGRAM_API_KEY
```

**Anthropic Claude:**
```python
ANTHROPIC_API_KEY
CLAUDE_MODEL = 'claude-3-haiku-20240307'  # Fast, efficient
CLAUDE_SYSTEM_PROMPT = "..." (extensive prompt with routing rules)
```

**ElevenLabs:**
```python
ELEVENLABS_API_KEY
ELEVENLABS_VOICE_ID = '21m00Tcm4TlvDq8ikWAM'  # Rachel voice
ELEVENLABS_MODEL = 'eleven_turbo_v2_5'  # Low latency
```

**Conversation Tuning:**
```python
PAUSE_THRESHOLD = 0.3  # Seconds of silence before AI responds
RESPONSE_TIMEOUT = 15.0  # Max time for Claude/ElevenLabs
PREDICTIVE_RESPONSES = True  # Start generating on interim transcripts
INTERIM_STABILITY_THRESHOLD = 3  # Matching interims to trigger
```

**Database & Integrations:**
```python
DATABASE_URL  # PostgreSQL connection string
QUICKBOOKS_CLIENT_ID/SECRET  # OAuth credentials
QUICKBOOKS_REALM_ID  # Company ID
SALES_FORWARD_NUMBER  # Agent transfer number
```

**Critical System Prompt:** The Claude system prompt is extensive (~100 lines) and includes:
- Response speed requirements (1-2 sentences max)
- Call transfer capability markers (`[TRANSFER_TO_SALES]`)
- Detergent order workflow markers (`[COLLECT_DETERGENT_NAME]`, etc.)
- Knowledge base integration from external file

---

### 3. **call_manager.py** - Call State Tracking

**Location:** `call_manager.py`
**Lines of Code:** 115
**Purpose:** Singleton pattern manager for active call metadata and transcripts

**Data Structure:**
```python
self.calls = {
    'CA1234567890': {
        'call_sid': 'CA1234567890',
        'caller_number': '+15551234567',
        'start_time': datetime(...),
        'transcripts': [
            {
                'text': 'Hello',
                'is_final': True,
                'speaker': 'Caller',
                'timestamp': datetime(...)
            }
        ]
    }
}
```

**Key Methods:**
- `create_call(call_sid, caller_number)` - Initialize call tracking
- `add_transcript(call_sid, text, is_final, speaker)` - Append transcript segments
- `end_call(call_sid)` - Save transcript to file and cleanup
- `_save_transcript(call)` - Generate timestamped file in `transcripts/`

**Transcript File Format:**
```
Call SID: CA1234567890
Caller: +15551234567
Start: 2025-12-02 10:30:15
End: 2025-12-02 10:32:45
Duration: 150.0 seconds

============================================================
TRANSCRIPT (Final only)
============================================================

[10:30:17] Caller: Hello, I need help with my order
[10:30:22] AI: I'd be happy to help. What's your order number?
[10:30:28] Caller: It's 12345
```

**Global Instance:**
```python
call_manager = CallManager()  # Singleton used throughout app
```

---

### 4. **deepgram_client.py** - Speech-to-Text Integration

**Location:** `deepgram_client.py`
**Lines of Code:** 126
**Purpose:** Manages WebSocket connection to Deepgram for real-time transcription

**Key Features:**
- **Model:** `nova-2-phonecall` - Optimized for telephony audio
- **Encoding:** mulaw, 8000 Hz, mono (matches Twilio format)
- **Enhancements:**
  - Punctuation enabled
  - Smart formatting (numbers, dates, times)
  - Filler word detection (um, uh)
  - Custom keywords: TEMCO, detergent, QuickBooks (2.0x boost)

**Callback Architecture:**
```python
def __init__(self, callback):
    self.callback = callback  # Called with (text, is_final)
```

**Message Handling:**
```python
def _on_message(self, message):
    # Parse Deepgram JSON response
    transcript = data['channel']['alternatives'][0]['transcript']
    is_final = data.get('is_final', False)
    self.callback(transcript, is_final)  # Invoke callback
```

**Performance Optimizations:**
- Keepalive messages every 250 chunks (5 seconds)
- Verbose logging removed to prevent event loop blocking
- First 3 chunks logged for debugging, then periodic summaries

**Connection Lifecycle:**
```python
await connect()  # Establish WebSocket
connection.send(audio_bytes)  # Stream audio
await close()  # Graceful shutdown
```

---

### 5. **conversation_manager.py** - Conversation State Machine

**Location:** `conversation_manager.py`
**Lines of Code:** 460
**Purpose:** State machine for managing conversation flow, pause detection, and barge-in handling

**State Definitions:**
```python
class ConversationState(Enum):
    IDLE = "idle"
    USER_SPEAKING = "user_speaking"
    WAITING_FOR_PAUSE = "waiting_for_pause"
    AI_THINKING = "ai_thinking"
    AI_SPEAKING = "ai_speaking"

    # Routing workflow states
    GREETING = "greeting"
    ROUTING_QUESTION = "routing_question"
    ANALYZING_INTENT = "analyzing_intent"
    CONFIRMING_ROUTE = "confirming_route"
    TRANSFERRING = "transferring"
    HUMAN_CONVERSATION = "human_conversation"

    # Legacy (detergent workflow - disabled)
    COLLECTING_CUSTOMER_INFO = "collecting_customer_info"
```

**Core Algorithms:**

**Pause Detection:**
```python
def check_for_pause(self) -> bool:
    if state != WAITING_FOR_PAUSE:
        return False

    time_since_last_speech = now - last_final_time

    if time_since_last_speech >= pause_threshold:  # Default: 0.3s
        state = AI_THINKING
        trigger_user_finished_callback()
        return True
```

**Barge-In Detection:**
```python
def add_transcript(text, is_final):
    if state == AI_SPEAKING:
        if ignore_barge_in:
            # Structured data collection mode
            state = USER_SPEAKING
            # Keep accumulated text
        else:
            # Normal mode: Stop AI immediately
            trigger_barge_in_callback()
            state = USER_SPEAKING
            current_user_text = ""  # Reset
```

**Predictive Response Triggering:**
- Tracks last N interim transcripts
- Calculates word-based similarity ratio
- If 3+ consecutive interims are >80% similar → Trigger early response generation
- Allows Claude/ElevenLabs to start processing before user finishes speaking

**Dynamic Pause Threshold:**
```python
# Normal conversation: 0.3s
set_pause_threshold_for_structured_data(2.5)  # Phone numbers, addresses
restore_default_pause_threshold()  # Back to 0.3s
```

**Conversation History Management:**
```python
conversation_history = [
    {'role': 'user', 'content': 'Hello'},
    {'role': 'assistant', 'content': 'Hi! How can I help?'},
    ...
]
```

**Callback System:**
```python
on_user_finished = callback  # Called when pause detected
on_barge_in = callback  # Called when user interrupts AI
on_predictive_trigger = callback  # Called for early response generation
```

**Detergent Order Fields** (Legacy - currently disabled):
- Name, phone, email, address (street/city/state/zip)
- Payment method, quantity
- QuickBooks customer lookup data
- Address confirmation flags

---

### 6. **claude_client.py** - AI Agent Interface

**Location:** `claude_client.py`
**Lines of Code:** 122
**Purpose:** Manages conversation with Anthropic Claude API

**Initialization:**
```python
def __init__(self, system_prompt=None, conversation_history=None):
    self.client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    self.model = 'claude-3-haiku-20240307'  # Fast, cost-effective
    self.system_prompt = system_prompt or Config.CLAUDE_SYSTEM_PROMPT
    self.conversation_history = conversation_history or []
```

**Async Request with Timeout:**
```python
async def get_response(self, user_text=None, timeout=15.0) -> str:
    response = await asyncio.wait_for(
        asyncio.to_thread(
            self.client.messages.create,
            model=self.model,
            max_tokens=150,  # Short responses for phone calls
            system=self.system_prompt,
            messages=self.conversation_history
        ),
        timeout=timeout
    )
    return response.content[0].text
```

**Key Configuration:**
- **Model:** Claude 3 Haiku - Optimized for speed/cost on phone calls
- **Max Tokens:** 150 (enforces concise responses)
- **Timeout:** 15 seconds with fallback message
- **Error Handling:** Graceful degradation on API failures

**Message Flow:**
```python
# Add user message
add_user_message("I need help with my order")

# Get response (adds to history automatically)
response = await get_response()

# History now contains:
# [{'role': 'user', 'content': '...'}, {'role': 'assistant', 'content': '...'}]
```

---

### 7. **elevenlabs_client.py** - Text-to-Speech Synthesis

**Location:** `elevenlabs_client.py`
**Lines of Code:** 189
**Purpose:** Converts Claude's text responses to phone-compatible audio

**Audio Pipeline:**
```
Text → ElevenLabs API → MP3 audio → pydub conversion → mulaw/8kHz/mono
```

**Implementation:**
```python
async def text_to_speech(self, text: str) -> bytes:
    # 1. Call ElevenLabs API
    audio_data = await _generate_speech(text)  # Returns MP3

    # 2. Convert to Twilio format
    converted_audio = await _convert_to_twilio_format(audio_data)

    return converted_audio  # Raw mulaw bytes
```

**Conversion Details:**
```python
async def _convert_to_twilio_format(self, audio_data: bytes) -> bytes:
    # Load MP3
    audio = AudioSegment.from_mp3(io.BytesIO(audio_data))

    # Convert to Twilio specs
    audio = audio.set_frame_rate(8000)  # 8kHz
    audio = audio.set_channels(1)  # Mono

    # Export as raw mulaw
    audio.export(buffer, format="mulaw", parameters=["-ar", "8000", "-ac", "1"])

    return buffer.read()
```

**Voice Configuration:**
```python
voice_settings = {
    "stability": 0.2,
    "similarity_boost": 0.99,
    "style": 0.8,
    "use_speaker_boost": True
}
```

**Dependency Check:**
- Graceful degradation if `requests` or `pydub` unavailable
- Python 3.14 compatibility warnings (audioop module issues)

---

### 8. **routing_engine.py** - Hybrid Call Routing System

**Location:** `routing_engine.py`
**Lines of Code:** 210
**Purpose:** Determines which department to route caller to

**Routing Strategy (Priority Order):**

1. **High-Confidence Keywords** (>90%)
   - Fast database lookup
   - Regex pattern matching with word boundaries
   - Priority-based rule ordering

2. **AI Analysis** (>80% confidence) - *Future Phase 3*
   - Semantic intent understanding
   - Context-aware routing
   - Currently commented out

3. **Medium-Confidence Keywords** (fallback)
   - Lower confidence keyword matches
   - Better than menu

4. **Interactive Menu**
   - Last resort if nothing matches
   - AI reads department options
   - User selects by voice

5. **Default Route** (Sales)
   - Ultimate fallback

**Routing Decision Structure:**
```python
@dataclass
class RoutingDecision:
    department: str  # 'Sales', 'Support', 'Billing'
    department_id: int
    phone_number: str  # Agent's phone number
    method: str  # 'keyword_match', 'ai_analysis', 'menu_selection'
    confidence: float  # 0.0 - 1.0
    reason: str  # "Matched keywords: order, purchase"
    needs_confirmation: bool
```

**Keyword Matching Logic:**
```python
def check_keyword_rules(self, text: str) -> Optional[RoutingDecision]:
    # Get active rules from database, ordered by priority
    rules = session.query(RoutingRule).filter_by(active=True).order_by(priority.desc())

    for rule in rules:
        matched_keywords = []

        for keyword in rule.keywords:
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            if re.search(pattern, text_lower):
                matched_keywords.append(keyword)

        # Check match criteria
        if rule.match_type == 'any' and len(matched_keywords) > 0:
            return high_confidence_decision(0.95)
        elif rule.match_type == 'all' and len(matched_keywords) == len(rule.keywords):
            return very_high_confidence_decision(0.98)
```

**Database Integration:**
- Reads from `routing_rules` and `departments` tables
- Supports dynamic rule updates without code changes
- Priority-based rule evaluation

---

### 9. **conference_manager.py** - Conference Bridge Tracking

**Location:** `conference_manager.py`
**Lines of Code:** 183
**Purpose:** Tracks Twilio conference rooms and participant state

**Conference Lifecycle:**
```python
# 1. Create conference for incoming call
conference_name = create_conference(call_sid, caller_phone)
# Returns: "call-room-CA1234567890"

# 2. Track participants
add_participant(conference_name, participant_sid, role='caller')
add_participant(conference_name, agent_participant_sid, role='agent')

# 3. Check state
is_agent_in_conference(call_sid)  # Returns True/False

# 4. Cleanup
cleanup_conference(conference_name)
```

**Conference Metadata Structure:**
```python
active_conferences = {
    'call-room-CA1234567890': {
        'call_sid': 'CA1234567890',
        'caller_phone': '+15551234567',
        'created_at': datetime.utcnow(),
        'participants': [
            {'sid': 'PA123', 'role': 'caller', 'joined_at': datetime(...)},
            {'sid': 'PA456', 'role': 'agent', 'joined_at': datetime(...)}
        ],
        'agent_joined': True,
        'caller_participant_sid': 'PA123',
        'agent_participant_sid': 'PA456',
        'recording_sid': 'RE789',
        'recording_url': 'https://...'
    }
}
```

**Key Features:**
- Participant join/leave tracking
- Recording metadata storage
- Conference statistics (total conferences, with agents, waiting)
- Duration calculation

**Critical for Media Stream Persistence:**
The conference bridge architecture allows the WebSocket media stream to remain active during agent transfer, enabling continuous transcription throughout the entire call.

---

### 10. **database.py** - Data Persistence Layer

**Location:** `database.py`
**Lines of Code:** 520
**Purpose:** SQLAlchemy ORM models and database operations

**Database Models:**

**1. DetergentOrder (Legacy - detergent workflow disabled)**
```python
class DetergentOrder(Base):
    id: Integer (PK)
    call_sid: String(100)
    customer_name: String(200)
    customer_phone: String(50)
    customer_email: String(200)
    address_street: String(300)
    address_city: String(100)
    address_state: String(50)
    address_zip: String(10)
    payment_method: String(100)
    quantity: Integer

    # QuickBooks sync
    qb_customer_id: String(50)
    qb_invoice_id: String(50)
    qb_invoice_number: String(50)
    sync_status: String(20)  # 'pending', 'synced', 'failed'
    sync_error: Text

    created_at: DateTime
    synced_at: DateTime
```

**2. Department**
```python
class Department(Base):
    id: Integer (PK)
    name: String(100) UNIQUE  # 'Sales', 'Support', 'Billing'
    phone_number: String(20)  # Agent/department phone
    description: Text
    active: Boolean  # Can be temporarily disabled
    priority: Integer  # Display order (higher = first)
    created_at: DateTime
    updated_at: DateTime
```

**3. RoutingRule**
```python
class RoutingRule(Base):
    id: Integer (PK)
    rule_name: String(100)  # "Order Keywords"
    keywords: ARRAY(String)  # ['order', 'purchase', 'buy']
    department_id: Integer (FK → departments.id)
    priority: Integer  # Higher = checked first
    active: Boolean
    match_type: String(20)  # 'any' or 'all'
    created_at: DateTime
    updated_at: DateTime
```

**4. CallRoute**
```python
class CallRoute(Base):
    id: Integer (PK)
    call_sid: String(100) UNIQUE
    caller_phone: String(50)
    routing_decision: String(100)  # Department chosen
    routing_method: String(50)  # 'keyword_match', 'ai_analysis', 'menu_selection'
    routing_reason: Text
    confidence_score: Numeric(3, 2)  # 0.00-1.00
    routed_to: String(100)  # Agent phone
    department_id: Integer (FK → departments.id)
    routed_at: DateTime
    agent_answered_at: DateTime
    call_ended_at: DateTime
    call_duration_seconds: Integer
    created_at: DateTime
```

**5. CallTranscript**
```python
class CallTranscript(Base):
    id: Integer (PK)
    call_sid: String(100)
    speaker: String(20)  # 'caller', 'agent', 'ai'
    text: Text
    is_final: Boolean
    confidence: Numeric(3, 2)
    timestamp: DateTime
    segment_number: Integer  # Order in conversation
    transcription_type: String(20)  # 'realtime' or 'batch' (diarized)
```

**6. CallMetadata**
```python
class CallMetadata(Base):
    call_sid: String(100) (PK)
    caller_phone: String(50)
    caller_name: String(200)
    routing_stage: String(50)  # 'greeting', 'routing', 'transferred', 'ended'
    conversation_summary: Text  # AI-generated post-call
    outcome: String(50)  # 'routed_successfully', 'no_answer', 'caller_hung_up'
    call_started_at: DateTime
    call_ended_at: DateTime
    total_duration_seconds: Integer
    created_at: DateTime
```

**Key Functions:**
```python
# Detergent orders
create_order(order_data) → order_id
update_sync_status(order_id, status, qb_data=None, error=None)
get_pending_orders() → List[DetergentOrder]

# Call routing
create_call_route(route_data) → route_id
update_call_route_end(call_sid, agent_answered_at, call_ended_at, duration)

# Transcripts
create_transcript(call_sid, speaker, text, is_final, confidence, type)
get_call_transcripts(call_sid, final_only=True) → List[CallTranscript]
```

**Session Management:**
```python
def get_session():
    if Session is None:
        init_db()  # Lazy initialization
    return Session()

# Usage pattern:
session = get_session()
try:
    # Query/insert operations
    session.commit()
finally:
    session.close()  # Always close
```

---

### 11. **admin_routes.py** - Web Dashboard (Not detailed in reads, but mentioned)

**Purpose:** Flask Blueprint for admin interface
- View recent orders
- Monitor sync status
- Manual retry for failed syncs
- Call routing analytics
- Transcript viewer

---

### 12. **quickbooks_client.py** - ERP Integration (Not detailed in reads, but mentioned)

**Purpose:** QuickBooks Online API integration
- OAuth 2.0 authentication flow
- Customer lookup by name/phone
- Invoice generation for detergent orders
- Token refresh management

---

### 13. **websocket_handler.py** - Alternative WebSocket Implementation

**Location:** `websocket_handler.py`
**Lines of Code:** 174
**Purpose:** SocketIO-based WebSocket handlers (currently NOT in use)

**Status:** This module is legacy code. The current implementation uses `flask-sock` directly in `app.py` instead of SocketIO. Kept for reference but not actively used.

**If Used, Would Provide:**
- `@socketio.on('connect', namespace='/media')`
- `@socketio.on('message', namespace='/media')`
- `@socketio.on('disconnect', namespace='/media')`

---

## Data Flow Diagrams

### 1. Incoming Call Flow

```
User Calls → Twilio
              ↓
        HTTP POST /voice
              ↓
     Generate TwiML Response:
     - <Say> greeting
     - <Connect><Stream> to /media
     - <Conference> call-room-{sid}
              ↓
     WebSocket /media opens
              ↓
     Audio chunks arrive (base64)
              ↓
     Decode → Queue → Deepgram
              ↓
     Transcripts → CallManager
              ↓
     ConversationManager detects pause
              ↓
     Claude generates response
              ↓
     ElevenLabs converts to audio
              ↓
     Stream back to caller via Twilio
```

### 2. Routing Decision Flow

```
User: "I need to order something"
              ↓
     RoutingEngine.determine_route()
              ↓
     1. Check keyword rules (DB query)
              ↓
     Match found: "order" keyword
              ↓
     Return RoutingDecision:
     - department: "Sales"
     - confidence: 0.95
     - method: "keyword_match"
              ↓
     Claude confirms: "I'll connect you to Sales"
              ↓
     Twilio Dial agent into conference
              ↓
     Agent joins → Media stream stays open
              ↓
     Continuous transcription continues
              ↓
     Save to CallRoute database table
```

### 3. Response Caching Flow (Startup)

```
Server Startup
     ↓
load_cached_responses_from_disk()
     ↓
Check cached_audio/*.ulaw files
     ↓
If missing → generate_cached_responses()
     ↓
For each common Q&A:
     - Claude generates text
     - ElevenLabs converts to audio
     - Convert to mulaw/8kHz/mono
     - Save to disk
     - Store in memory cache
     ↓
Runtime: Check cache before calling APIs
```

---

## Key Features & Optimizations

### 1. Response Caching System
- Pre-generates audio for common questions at startup
- Checks cache before calling Claude/ElevenLabs APIs
- Reduces latency from ~3-5s to ~500ms for cached responses
- Persistent cache: `cached_audio/*.ulaw` files
- Keyword matching: "how much", "price", "location", etc.

### 2. Predictive Response Generation
- Tracks interim transcripts from Deepgram
- If 3 consecutive interims are >80% similar → Start generating response
- Allows AI processing to begin before user finishes speaking
- Reduces perceived latency by ~1-2 seconds

### 3. Barge-In Detection
- Monitors for user speech during AI playback
- Immediately cancels AI audio stream
- Switches state to `USER_SPEAKING`
- Provides natural conversation flow

### 4. Dynamic Pause Thresholds
- Normal conversation: 0.3s pause triggers response
- Structured data (phone/address): 2.5s pause (allows digit-by-digit speech)
- Automatically restores default after collection completes

### 5. Continuous Transcription During Transfer
- WebSocket media stream persists through conference bridge
- Transcription continues when agent joins
- Enables post-call diarization (speaker identification)
- Saves complete conversation to database

### 6. Conference Bridge Architecture
- Allows seamless agent transfer without dropping call
- AI joins as participant, can leave when agent joins
- Media stream stays connected for transcription
- Supports call recording

---

## Configuration & Deployment

### Environment Variables Required

**Critical (Must Have):**
```bash
# Twilio
TWILIO_ACCOUNT_SID=ACxxxx
TWILIO_AUTH_TOKEN=xxxx
TWILIO_PHONE_NUMBER=+15551234567

# Deepgram
DEEPGRAM_API_KEY=xxxx

# Anthropic
ANTHROPIC_API_KEY=sk-ant-xxxx
CLAUDE_MODEL=claude-3-haiku-20240307

# ElevenLabs
ELEVENLABS_API_KEY=xxxx
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# WebSocket URL (Production)
WEBSOCKET_URL=wss://your-domain.com/media
BASE_URL=https://your-domain.com
```

**Optional (With Defaults):**
```bash
# Conversation Tuning
PAUSE_THRESHOLD=0.3
RESPONSE_TIMEOUT=15.0
PREDICTIVE_RESPONSES=True
INTERIM_STABILITY_THRESHOLD=3

# Call Routing
SALES_FORWARD_NUMBER=+18166741783

# QuickBooks (if using detergent workflow)
QUICKBOOKS_CLIENT_ID=xxxx
QUICKBOOKS_CLIENT_SECRET=xxxx
QUICKBOOKS_REALM_ID=xxxx
QUICKBOOKS_REFRESH_TOKEN=xxxx

# Admin Dashboard
ADMIN_PASSWORD=changeme123
ADMIN_ENABLED=true

# Flask
PORT=5000
DEBUG=False
```

### Running the Application

**Development:**
```bash
python app.py
```

**Production (Gunicorn):**
```bash
gunicorn -c gunicorn_config.py app:app
```

**Gunicorn Configuration:**
- Worker class: `sync` (handles threading internally)
- Workers: 4 (adjust based on CPU cores)
- Timeout: 120s (for long-running requests)
- Bind: `0.0.0.0:5000`

### Dependencies

**Core:**
```
flask
flask-sock
twilio
deepgram-sdk==2.12.0
anthropic
requests
pydub
sqlalchemy
psycopg2-binary
python-dotenv
```

**System Requirements:**
- Python 3.8+
- FFmpeg (for pydub audio conversion)
- PostgreSQL 12+ (for database)

---

## Security Considerations

### 1. Webhook Authentication
- Twilio request validation (signature verification)
- Only accept requests from Twilio IPs

### 2. Secrets Management
- All API keys in environment variables
- Never commit `.env` file to version control
- Use secret management service in production (AWS Secrets Manager, etc.)

### 3. Database Security
- Use read-only credentials where possible
- Connection pooling with SQLAlchemy
- Prepared statements (ORM) prevent SQL injection

### 4. WebSocket Security
- TLS/SSL required (wss:// protocol)
- Origin checking for WebSocket connections
- Rate limiting on endpoints

### 5. PII Handling
- Transcripts contain phone numbers, names, addresses
- Encrypt at rest (PostgreSQL encryption)
- GDPR compliance: Data retention policies, deletion endpoints

---

## Monitoring & Observability

### Logging Strategy

**Console Logging:**
- All modules use consistent `[ModuleName]` prefixes
- Example: `[Deepgram] Connected`, `[Claude] Response (150 chars): '...'`
- Severity levels implied by symbols: ✓, ✅, ❌, ⚠️, 🔴, 🚀

**Log Locations:**
- Real-time: stdout (captured by gunicorn/systemd)
- Transcripts: `transcripts/{timestamp}.txt`
- Cached audio: `cached_audio/*.ulaw`

**Key Metrics to Monitor:**
- Deepgram connection latency
- Claude API response time
- ElevenLabs TTS generation time
- Total call duration
- Transfer success rate
- Routing accuracy (keyword vs fallback)

### Health Check Endpoint

```python
@app.route('/')
def index():
    return {'status': 'OK', 'service': 'Phone Agent'}
```

---

## Known Limitations & Technical Debt

### Current Limitations

1. **Detergent Workflow Disabled**
   - Feature flag: `DETERGENT_WORKFLOW_ENABLED = False`
   - Code remains but inactive (see lines 49-52 in app.py)
   - Database tables still exist

2. **AI Routing Not Implemented**
   - Routing engine has placeholder for AI analysis (Phase 3)
   - Currently relies on keyword matching only
   - Lines 49-53 in `routing_engine.py` commented out

3. **Single Conference per Call**
   - No support for call parking or multiple transfers
   - Conference name tied to call_sid (1:1 mapping)

4. **No WebRTC Support**
   - Relies entirely on Twilio telephony network
   - Cannot handle browser-based calls directly

5. **Python 3.14 Compatibility**
   - pydub may fail on Python 3.14 (audioop module removed)
   - Warning logged but doesn't crash

### Technical Debt

1. **websocket_handler.py Unused**
   - Old SocketIO implementation still in codebase
   - Should be removed or documented as deprecated

2. **Hard-coded Configuration**
   - Some TwiML URLs hard-coded in app.py
   - Should use Config.BASE_URL consistently

3. **Limited Error Recovery**
   - If Deepgram disconnects mid-call, no automatic reconnection
   - Requires call restart

4. **Transcript Deduplication**
   - Basic string matching to detect duplicate finals
   - Could be more robust with hashing

5. **No Call Queueing**
   - If all agents busy, call fails or goes to default route
   - No hold music or queue position announcements

---

## Future Enhancements (Roadmap)

### Phase 1 (Current)
- ✅ Real-time transcription
- ✅ Basic routing (keyword-based)
- ✅ Call transfer to agents
- ✅ Database logging

### Phase 2 (In Progress)
- Conference recording with diarization
- Post-call transcript processing (speaker labels)
- Enhanced admin dashboard
- Call analytics and reporting

### Phase 3 (Planned)
- AI-powered routing (Claude intent analysis)
- Multi-agent routing strategies
- Call queueing and hold music
- WebRTC support for browser calls
- Voice activity detection (VAD) improvements

### Phase 4 (Future)
- Real-time sentiment analysis
- Multi-language support
- Custom wake words for AI activation
- Integration with CRM systems (Salesforce, HubSpot)
- Voicemail transcription and summarization

---

## Troubleshooting Guide

### Common Issues

**1. No audio in calls**
- Check WEBSOCKET_URL is accessible from Twilio
- Verify TLS/SSL certificate valid (wss://)
- Check firewall allows WebSocket connections

**2. Deepgram not transcribing**
- Verify DEEPGRAM_API_KEY is valid
- Check audio format: mulaw, 8kHz, mono
- Look for connection errors in logs

**3. Claude responses timeout**
- Default timeout: 15s (Config.RESPONSE_TIMEOUT)
- Check ANTHROPIC_API_KEY
- Network latency to Claude API

**4. ElevenLabs audio garbled**
- Verify audio conversion to mulaw
- Check FFmpeg installed (`which ffmpeg`)
- Inspect `temp_audio/` files for debugging

**5. Agent transfer fails**
- Verify SALES_FORWARD_NUMBER is correct E.164 format
- Check Twilio account balance
- Look for conference creation errors in logs

---

## Testing Strategy

### Unit Tests
- Test individual modules in isolation
- Mock external APIs (Twilio, Deepgram, Claude, ElevenLabs)
- Focus on business logic and state machines

### Integration Tests
- Test end-to-end call flows
- Use Twilio test credentials
- Verify database writes

### Load Testing
- Simulate concurrent calls
- Measure WebSocket connection limits
- Test database connection pooling

### Manual Testing Checklist
- [ ] Incoming call connects
- [ ] Audio transcription working
- [ ] AI responds to questions
- [ ] Routing decisions accurate
- [ ] Agent transfer successful
- [ ] Transcripts saved correctly
- [ ] Admin dashboard accessible

---

## Appendix

### A. Audio Format Specifications

**Twilio Media Stream Format:**
- Encoding: G.711 μ-law
- Sample Rate: 8000 Hz
- Channels: 1 (mono)
- Bit Depth: 8-bit
- Codec: PCMU
- Container: None (raw)

**ElevenLabs Output:**
- Format: MP3
- Sample Rate: 44100 Hz (default)
- Channels: 1 or 2
- Bit Rate: Variable

**Conversion Required:**
- MP3 → WAV (pydub) → mulaw/8kHz/mono (FFmpeg)

### B. Twilio TwiML Reference

**Incoming Call Response (/voice):**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">Please wait while I connect your call.</Say>
    <Connect>
        <Stream url="wss://your-domain.com/media"/>
    </Connect>
    <Conference>call-room-CA1234567890</Conference>
</Response>
```

### C. Database Schema Diagram

```
┌─────────────────┐       ┌──────────────┐
│ DetergentOrder  │       │ Department   │
├─────────────────┤       ├──────────────┤
│ id (PK)         │       │ id (PK)      │
│ call_sid        │       │ name         │
│ customer_name   │       │ phone_number │
│ sync_status     │       │ active       │
└─────────────────┘       └──────────────┘
                                  │
                                  │ FK
                                  ▼
                          ┌──────────────┐
                          │ RoutingRule  │
                          ├──────────────┤
                          │ id (PK)      │
                          │ keywords[]   │
                          │ department_id│
                          └──────────────┘
                                  │
                                  │ FK
                                  ▼
┌─────────────────┐       ┌──────────────┐
│ CallRoute       │───────│ CallTranscript│
├─────────────────┤       ├──────────────┤
│ call_sid (PK)   │       │ call_sid     │
│ routing_method  │       │ speaker      │
│ department_id   │       │ text         │
└─────────────────┘       └──────────────┘
```

---

## Conclusion

This Phone Agent system represents a modern approach to telephony automation, combining real-time speech processing, AI-driven conversation, and intelligent routing. The architecture prioritizes low latency, reliability, and continuous transcription throughout the call lifecycle.

Key architectural decisions:
- **Multi-threaded audio pipeline** for real-time processing
- **State machine-based conversation management** for predictable behavior
- **Conference bridge architecture** enabling continuous transcription during transfers
- **Hybrid routing engine** balancing speed (keywords) and intelligence (AI - future)
- **Response caching** for sub-second latency on common queries

The system is production-ready for the current routing workflow, with clear extension points for AI-powered routing, multi-language support, and advanced analytics.

---

**Document Version:** 1.0
**Last Updated:** December 2, 2025
**Maintained By:** Development Team
**Review Schedule:** Quarterly or on major architecture changes
