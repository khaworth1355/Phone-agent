# Call Routing System Transformation Plan

**Project**: Transform Detergent Ordering AI → Intelligent Call Routing System
**Status**: Planning Complete ✅
**Date**: 2025-11-05

---

## 📋 Executive Summary

Transform the current phone agent from a detergent ordering system into an **intelligent call routing system** that:
- ✅ Answers calls and responds to quick questions (cached responses + knowledge base remain)
- ✅ Uses **hybrid routing** (AI conversation + keywords + menu fallback)
- ✅ Routes to **multiple departments** (Sales, Support, Billing, etc.)
- ✅ **Continues transcribing** caller-to-human conversations after routing
- ✅ Stores all routing decisions and transcripts in **database**
- ✅ Provides **admin interface** for database-driven routing rules (no code changes needed)

---

## 🎯 Key Requirements (From User)

1. **Primary Function**: Determine who to route calls to after initial greeting
2. **Routing Destinations**: Multiple departments (Sales, Support, etc.)
3. **Routing Method**: Hybrid approach (AI + keywords + menu)
4. **Existing Code**: Preserve detergent/QuickBooks code (disable, don't delete)
5. **Configuration**: Database-driven routing rules (configurable without deployment)
6. **Transcription**: Continue recording caller + human agent conversation after transfer
7. **Storage**: All transcripts in database

---

## 🔍 Critical Technical Finding

### Problem: Current Transfer Method Kills Transcription

**Current Implementation:**
```python
# transfer_call() in app.py line 661
twilio_client.calls(call_sid).update(twiml=f'''
    <Response>
        <Say>Transferring you now</Say>
        <Dial>{phone_number}</Dial>
    </Response>
''')
```

**Issue**: When `<Dial>` executes, it **replaces the active TwiML**, which:
- Terminates the `<Stream>` WebSocket connection
- Stops Deepgram from receiving audio
- Ends transcription immediately

**Result**: ❌ Cannot transcribe caller-to-human conversation

---

## ✅ Solution: Conference-Based Architecture

### Why Conferences?

**Architecture:**
```
Caller → Twilio Conference Room ← Human Agent (dialed in programmatically)
                ↓
         Media Stream (stays active)
                ↓
            Deepgram
                ↓
    Continuous Transcription (caller + agent)
```

**Benefits:**
1. Media Stream remains active throughout call
2. Conference captures audio from all participants
3. Can dial multiple agents if needed
4. Easy to add/remove participants programmatically
5. Twilio Conference events provide participant tracking

**TwiML Change:**
```xml
<!-- OLD: Direct dial (kills stream) -->
<Response>
    <Stream url="wss://server/media"/>
    <Dial>+18005551234</Dial>  <!-- Stream dies here -->
</Response>

<!-- NEW: Conference (keeps stream alive) -->
<Response>
    <Stream url="wss://server/media"/>
    <Dial>
        <Conference>call-room-{call_sid}</Conference>
    </Dial>
</Response>

<!-- Then separately dial agent into same conference via REST API -->
```

---

## 📅 5-Phase Implementation Plan

### **PHASE 1: Conference Architecture Foundation** 🏗️

**Goal**: Enable continuous transcription through call transfer

**Priority**: CRITICAL - Must be implemented first (blocks all other features)

#### Changes Required:

**1. Modify `/voice` Endpoint** (app.py ~line 453)

**Current Code:**
```python
# Line 500-503
start = Start()
stream = start.stream(url=Config.WEBSOCKET_URL)
stream.parameter(name='track', value='inbound_track')  # Only caller
response.append(start)
response.pause(length=600)  # Keep call open
```

**New Code:**
```python
# Start media stream
start = Start()
stream = start.stream(url=Config.WEBSOCKET_URL)
stream.parameter(name='track', value='both_tracks')  # Capture both speakers
response.append(start)

# Join conference room
dial = Dial()
conference_name = f"call-room-{call_sid}"
dial.conference(
    conference_name,
    start_conference_on_enter=True,
    end_conference_on_exit=True,
    wait_url=Config.CONFERENCE_WAIT_URL,  # Hold music
    status_callback=f"{Config.BASE_URL}/conference-status",
    status_callback_event="start end join leave"
)
response.append(dial)
```

**2. Create `conference_manager.py`** (NEW FILE)

```python
"""
Conference Manager - Track active conferences and participants
"""
from datetime import datetime

class ConferenceManager:
    def __init__(self):
        self.active_conferences = {}  # conference_name -> metadata

    def create_conference(self, call_sid, caller_phone):
        """Register new conference room"""
        conference_name = f"call-room-{call_sid}"
        self.active_conferences[conference_name] = {
            'call_sid': call_sid,
            'caller_phone': caller_phone,
            'created_at': datetime.utcnow(),
            'participants': [],
            'agent_joined': False
        }
        return conference_name

    def add_participant(self, conference_name, participant_sid, role):
        """Track when agent joins conference"""
        if conference_name in self.active_conferences:
            self.active_conferences[conference_name]['participants'].append({
                'sid': participant_sid,
                'role': role,  # 'caller' or 'agent'
                'joined_at': datetime.utcnow()
            })
            if role == 'agent':
                self.active_conferences[conference_name]['agent_joined'] = True

    def get_conference_info(self, call_sid):
        """Get conference metadata by call_sid"""
        conference_name = f"call-room-{call_sid}"
        return self.active_conferences.get(conference_name)

    def cleanup_conference(self, conference_name):
        """Remove conference after call ends"""
        if conference_name in self.active_conferences:
            del self.active_conferences[conference_name]

# Global instance
conference_manager = ConferenceManager()
```

**3. Add `/dial-agent` Endpoint** (app.py)

```python
@app.route('/dial-agent', methods=['POST'])
def dial_agent():
    """
    Dial human agent into active conference
    Called after routing decision is made

    POST body: {
        "call_sid": "CA123...",
        "department": "Sales",
        "agent_phone": "+18166741783"
    }
    """
    data = request.json
    call_sid = data['call_sid']
    agent_phone = data['agent_phone']
    department = data['department']

    conference_name = f"call-room-{call_sid}"

    # Create outbound call to agent
    call = twilio_client.calls.create(
        to=agent_phone,
        from_=Config.TWILIO_PHONE_NUMBER,
        twiml=f'''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Joanna">
                Connecting you to a caller from {department}.
            </Say>
            <Dial>
                <Conference>{conference_name}</Conference>
            </Dial>
        </Response>'''
    )

    # Log routing decision
    from database import create_call_route
    create_call_route({
        'call_sid': call_sid,
        'routing_decision': department,
        'routed_to': agent_phone,
        'routed_at': datetime.utcnow()
    })

    print(f"[Conference] Dialing {agent_phone} into {conference_name}")
    return jsonify({'status': 'success', 'call_sid': call.sid})
```

**4. Add `/conference-status` Webhook** (app.py)

```python
@app.route('/conference-status', methods=['POST'])
def conference_status():
    """
    Twilio webhook for conference events
    Events: start, end, join, leave
    """
    event = request.form.get('StatusCallbackEvent')
    conference_sid = request.form.get('ConferenceSid')
    call_sid = request.form.get('CallSid')
    friendly_name = request.form.get('FriendlyName')  # "call-room-{call_sid}"

    print(f"[Conference] Event: {event}, Conference: {friendly_name}, Call: {call_sid}")

    if event == 'participant-join':
        # Track who joined
        participant_label = request.form.get('ParticipantLabel')
        conference_manager.add_participant(friendly_name, call_sid, role='agent')

    elif event == 'conference-end':
        # Cleanup
        conference_manager.cleanup_conference(friendly_name)

    return ('', 200)
```

**5. Update Audio Capture** (app.py ~line 501)

**Change:**
```python
# OLD: Only capture caller
stream.parameter(name='track', value='inbound_track')

# NEW: Capture both caller and agent
stream.parameter(name='track', value='both_tracks')
```

#### Testing Phase 1:
- [ ] Call system, verify conference room created
- [ ] Check Media Stream WebSocket stays active
- [ ] Manually dial test phone number into conference
- [ ] Verify Deepgram captures audio from both participants
- [ ] Check conference events logged correctly

---

### **PHASE 2: Database Schema for Routing** 💾

**Goal**: Store routing rules, decisions, and transcripts in database

#### New Tables:

**1. `departments` Table**
```sql
CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,  -- 'Sales', 'Support', 'Billing', etc.
    phone_number VARCHAR(20) NOT NULL,  -- Destination phone (agent or dept line)
    description TEXT,                   -- "Handles new orders and account upgrades"
    active BOOLEAN DEFAULT TRUE,        -- Can be temporarily disabled
    priority INTEGER DEFAULT 0,         -- Display order in menu
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Initial seed data
INSERT INTO departments (name, phone_number, description, priority) VALUES
    ('Sales', '+18166741783', 'New orders and product inquiries', 1),
    ('Support', '+18005551234', 'Technical issues and troubleshooting', 2),
    ('Billing', '+18005555678', 'Billing questions and account management', 3);
```

**2. `routing_rules` Table**
```sql
CREATE TABLE routing_rules (
    id SERIAL PRIMARY KEY,
    rule_name VARCHAR(100) NOT NULL,    -- "Order Keywords" or "Support Issues"
    keywords TEXT[] NOT NULL,           -- Array: ['order', 'purchase', 'buy', 'detergent']
    department_id INTEGER REFERENCES departments(id),
    priority INTEGER DEFAULT 0,         -- Higher = checked first
    active BOOLEAN DEFAULT TRUE,
    match_type VARCHAR(20) DEFAULT 'any', -- 'any' or 'all' keywords must match
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Initial seed data
INSERT INTO routing_rules (rule_name, keywords, department_id, priority) VALUES
    ('Order Keywords', ARRAY['order', 'purchase', 'buy', 'detergent', 'place order'], 1, 100),
    ('Support Issues', ARRAY['problem', 'issue', 'broken', 'not working', 'help'], 2, 90),
    ('Billing Questions', ARRAY['bill', 'charge', 'payment', 'invoice', 'account'], 3, 80);
```

**3. `call_routes` Table**
```sql
CREATE TABLE call_routes (
    id SERIAL PRIMARY KEY,
    call_sid VARCHAR(100) NOT NULL UNIQUE,
    caller_phone VARCHAR(50),
    routing_decision VARCHAR(100),      -- Department name chosen
    routing_method VARCHAR(50),         -- 'ai_analysis', 'keyword_match', 'menu_selection'
    routing_reason TEXT,                -- Explanation: "Matched keywords: order, purchase"
    confidence_score DECIMAL(3,2),      -- AI confidence 0.00-1.00 (NULL for keyword/menu)
    routed_to VARCHAR(100),             -- Agent phone number or name
    department_id INTEGER REFERENCES departments(id),
    routed_at TIMESTAMP,                -- When transfer was initiated
    agent_answered_at TIMESTAMP,        -- When agent joined conference (NULL if no answer)
    call_ended_at TIMESTAMP,            -- When call disconnected
    call_duration_seconds INTEGER,      -- Total call duration
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_call_routes_call_sid ON call_routes(call_sid);
CREATE INDEX idx_call_routes_department ON call_routes(department_id);
CREATE INDEX idx_call_routes_created_at ON call_routes(created_at);
```

**4. `call_transcripts` Table**
```sql
CREATE TABLE call_transcripts (
    id SERIAL PRIMARY KEY,
    call_sid VARCHAR(100) NOT NULL,
    speaker VARCHAR(20) NOT NULL,       -- 'caller', 'agent', 'ai'
    text TEXT NOT NULL,                 -- Transcript text
    is_final BOOLEAN DEFAULT FALSE,     -- TRUE for final, FALSE for interim
    confidence DECIMAL(3,2),            -- Deepgram confidence score
    timestamp TIMESTAMP DEFAULT NOW(),
    segment_number INTEGER,             -- Order in conversation (1, 2, 3...)

    CONSTRAINT check_speaker CHECK (speaker IN ('caller', 'agent', 'ai'))
);

CREATE INDEX idx_transcripts_call_sid ON call_transcripts(call_sid);
CREATE INDEX idx_transcripts_timestamp ON call_transcripts(timestamp);
CREATE INDEX idx_transcripts_speaker ON call_transcripts(speaker);
```

**5. `calls_metadata` Table (Optional - Enhanced Call Tracking)**
```sql
CREATE TABLE calls_metadata (
    call_sid VARCHAR(100) PRIMARY KEY,
    caller_phone VARCHAR(50),
    caller_name VARCHAR(200),           -- If recognized from QuickBooks
    routing_stage VARCHAR(50),          -- Current stage: 'greeting', 'routing', 'transferred', 'ended'
    conversation_summary TEXT,          -- AI-generated summary (generated after call ends)
    outcome VARCHAR(50),                -- 'routed_successfully', 'no_answer', 'caller_hung_up', 'voicemail'
    call_started_at TIMESTAMP,
    call_ended_at TIMESTAMP,
    total_duration_seconds INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Files to Create/Modify:

**Create: `migrations/add_routing_schema.py`**
```python
"""
Database migration: Add call routing tables
Run once: python migrations/add_routing_schema.py
"""
from sqlalchemy import create_engine, text
from config import Config

def add_routing_schema():
    engine = create_engine(Config.DATABASE_URL)

    with engine.connect() as conn:
        # Read SQL from file
        with open('migrations/routing_schema.sql', 'r') as f:
            sql = f.read()

        # Execute
        for statement in sql.split(';'):
            if statement.strip():
                conn.execute(text(statement))
                conn.commit()

        print("✓ Routing schema created successfully")

if __name__ == "__main__":
    add_routing_schema()
```

**Modify: `database.py`**

Add new SQLAlchemy models:
```python
class Department(Base):
    __tablename__ = 'departments'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    phone_number = Column(String(20), nullable=False)
    description = Column(Text)
    active = Column(Boolean, default=True)
    priority = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RoutingRule(Base):
    __tablename__ = 'routing_rules'
    id = Column(Integer, primary_key=True)
    rule_name = Column(String(100), nullable=False)
    keywords = Column(ARRAY(String))  # PostgreSQL array type
    department_id = Column(Integer, ForeignKey('departments.id'))
    priority = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    match_type = Column(String(20), default='any')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    department = relationship('Department', backref='routing_rules')

class CallRoute(Base):
    __tablename__ = 'call_routes'
    id = Column(Integer, primary_key=True)
    call_sid = Column(String(100), unique=True, nullable=False)
    caller_phone = Column(String(50))
    routing_decision = Column(String(100))
    routing_method = Column(String(50))
    routing_reason = Column(Text)
    confidence_score = Column(Numeric(3, 2))
    routed_to = Column(String(100))
    department_id = Column(Integer, ForeignKey('departments.id'))
    routed_at = Column(DateTime)
    agent_answered_at = Column(DateTime)
    call_ended_at = Column(DateTime)
    call_duration_seconds = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    department = relationship('Department', backref='call_routes')

class CallTranscript(Base):
    __tablename__ = 'call_transcripts'
    id = Column(Integer, primary_key=True)
    call_sid = Column(String(100), nullable=False)
    speaker = Column(String(20), nullable=False)
    text = Column(Text, nullable=False)
    is_final = Column(Boolean, default=False)
    confidence = Column(Numeric(3, 2))
    timestamp = Column(DateTime, default=datetime.utcnow)
    segment_number = Column(Integer)

class CallMetadata(Base):
    __tablename__ = 'calls_metadata'
    call_sid = Column(String(100), primary_key=True)
    caller_phone = Column(String(50))
    caller_name = Column(String(200))
    routing_stage = Column(String(50))
    conversation_summary = Column(Text)
    outcome = Column(String(50))
    call_started_at = Column(DateTime)
    call_ended_at = Column(DateTime)
    total_duration_seconds = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

# Add helper functions
def create_call_route(route_data):
    session = get_session()
    try:
        route = CallRoute(**route_data)
        session.add(route)
        session.commit()
        return route.id
    finally:
        session.close()

def create_transcript(call_sid, speaker, text, is_final, confidence=None):
    session = get_session()
    try:
        # Get last segment number
        last_segment = session.query(CallTranscript).filter_by(
            call_sid=call_sid
        ).order_by(CallTranscript.segment_number.desc()).first()

        segment_number = (last_segment.segment_number + 1) if last_segment else 1

        transcript = CallTranscript(
            call_sid=call_sid,
            speaker=speaker,
            text=text,
            is_final=is_final,
            confidence=confidence,
            segment_number=segment_number
        )
        session.add(transcript)
        session.commit()
    finally:
        session.close()
```

**Modify: `detergent_orders` Table (Optional)**
```sql
-- Add archived flag to preserve old data without deleting
ALTER TABLE detergent_orders ADD COLUMN archived BOOLEAN DEFAULT FALSE;

-- Mark existing orders as archived (optional)
UPDATE detergent_orders SET archived = TRUE;
```

#### Testing Phase 2:
- [ ] Run migration script successfully
- [ ] Verify all 5 tables created in database
- [ ] Insert test departments via SQL
- [ ] Insert test routing rules
- [ ] Query tables via SQLAlchemy models

---

### **PHASE 3: Routing Intelligence & State Machine** 🧠

**Goal**: Replace detergent workflow with routing logic

#### A. Update Conversation States

**Modify: `conversation_manager.py`**

**Old States:**
```python
class ConversationState(Enum):
    IDLE = "idle"
    USER_SPEAKING = "user_speaking"
    WAITING_FOR_PAUSE = "waiting_for_pause"
    AI_THINKING = "ai_thinking"
    AI_SPEAKING = "ai_speaking"
    COLLECTING_CUSTOMER_INFO = "collecting_customer_info"  # Detergent-specific
```

**New States:**
```python
class ConversationState(Enum):
    IDLE = "idle"
    USER_SPEAKING = "user_speaking"
    WAITING_FOR_PAUSE = "waiting_for_pause"
    AI_THINKING = "ai_thinking"
    AI_SPEAKING = "ai_speaking"

    # NEW: Routing workflow states
    GREETING = "greeting"                      # Playing initial message
    ROUTING_QUESTION = "routing_question"      # Asking "How can I help?"
    ANALYZING_INTENT = "analyzing_intent"      # Processing routing decision
    CONFIRMING_ROUTE = "confirming_route"      # "I'll connect you to Sales, ok?"
    TRANSFERRING = "transferring"              # Dialing agent into conference
    HUMAN_CONVERSATION = "human_conversation"  # Human agent handling call
    CALL_ENDED = "call_ended"

    # LEGACY: Keep for reference but unused
    # COLLECTING_CUSTOMER_INFO = "collecting_customer_info"
```

Add routing-specific fields:
```python
class ConversationManager:
    def __init__(self, call_sid: str):
        # ... existing fields ...

        # NEW: Routing workflow fields
        self.routing_decision_made = False
        self.routing_department = None
        self.routing_confidence = None
        self.routing_method = None  # 'ai', 'keyword', 'menu'
        self.awaiting_routing_confirmation = False
        self.agent_joined_at = None
```

#### B. Create Routing Engine

**Create: `routing_engine.py`** (NEW FILE)

```python
"""
Routing Engine - Hybrid AI + Keyword + Menu routing system
Determines which department to route caller to based on conversation
"""
import re
from typing import Optional, Dict, List
from dataclasses import dataclass
from database import get_session, Department, RoutingRule

@dataclass
class RoutingDecision:
    department: str
    department_id: int
    phone_number: str
    method: str  # 'ai_analysis', 'keyword_match', 'menu_selection'
    confidence: float  # 0.0 - 1.0
    reason: str
    needs_confirmation: bool


class RoutingEngine:
    def __init__(self):
        self.confidence_threshold = 0.8  # From config
        self.menu_fallback_enabled = True

    def determine_route(self, user_text: str, conversation_history: list) -> RoutingDecision:
        """
        Main routing logic: Try AI → Keywords → Menu

        Args:
            user_text: Latest user utterance
            conversation_history: Full conversation for context

        Returns:
            RoutingDecision with department and confidence
        """
        print(f"[RoutingEngine] Analyzing: '{user_text}'")

        # 1. Try keyword matching first (fast)
        keyword_match = self.check_keyword_rules(user_text)
        if keyword_match and keyword_match.confidence >= 0.9:
            print(f"[RoutingEngine] ✓ High-confidence keyword match: {keyword_match.department}")
            return keyword_match

        # 2. Use AI for intelligent analysis
        ai_decision = self.ai_analyze_intent(user_text, conversation_history)
        if ai_decision and ai_decision.confidence >= self.confidence_threshold:
            print(f"[RoutingEngine] ✓ AI routing: {ai_decision.department} ({ai_decision.confidence})")
            return ai_decision

        # 3. Fall back to keyword if AI uncertain
        if keyword_match:
            print(f"[RoutingEngine] ✓ Keyword fallback: {keyword_match.department}")
            return keyword_match

        # 4. Present menu as last resort
        if self.menu_fallback_enabled:
            print(f"[RoutingEngine] → Presenting menu (no clear match)")
            return self.present_menu()

        # 5. Default to Sales if all else fails
        return self.get_default_route()

    def check_keyword_rules(self, text: str) -> Optional[RoutingDecision]:
        """
        Check database routing rules for keyword matches
        Returns highest priority match
        """
        text_lower = text.lower()
        session = get_session()

        try:
            # Get active rules ordered by priority
            rules = session.query(RoutingRule).filter_by(
                active=True
            ).order_by(
                RoutingRule.priority.desc()
            ).all()

            for rule in rules:
                matched_keywords = []

                for keyword in rule.keywords:
                    # Use word boundaries for exact matching
                    pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                    if re.search(pattern, text_lower):
                        matched_keywords.append(keyword)

                # Check if match criteria met
                if rule.match_type == 'any' and len(matched_keywords) > 0:
                    # Any keyword matches
                    dept = rule.department
                    return RoutingDecision(
                        department=dept.name,
                        department_id=dept.id,
                        phone_number=dept.phone_number,
                        method='keyword_match',
                        confidence=0.95,  # High confidence for keyword
                        reason=f"Matched keywords: {', '.join(matched_keywords)}",
                        needs_confirmation=False
                    )
                elif rule.match_type == 'all' and len(matched_keywords) == len(rule.keywords):
                    # All keywords must match
                    dept = rule.department
                    return RoutingDecision(
                        department=dept.name,
                        department_id=dept.id,
                        phone_number=dept.phone_number,
                        method='keyword_match',
                        confidence=0.98,  # Very high confidence
                        reason=f"Matched all keywords: {', '.join(matched_keywords)}",
                        needs_confirmation=False
                    )

            return None

        finally:
            session.close()

    def ai_analyze_intent(self, user_text: str, conversation_history: list) -> Optional[RoutingDecision]:
        """
        Use Claude AI to intelligently analyze routing intent
        """
        from claude_agent import ClaudeAgent

        # Get available departments
        session = get_session()
        departments = session.query(Department).filter_by(active=True).all()
        session.close()

        dept_list = "\n".join([f"- {d.name}: {d.description}" for d in departments])

        # Build routing analysis prompt
        prompt = f"""You are a call routing assistant. Based on the caller's request, determine which department should handle their call.

Available departments:
{dept_list}

Recent conversation:
{self._format_history(conversation_history)}

Caller's latest message: "{user_text}"

Analyze the caller's intent and respond in JSON format:
{{
    "department": "Sales|Support|Billing|Unknown",
    "confidence": 0.85,
    "reasoning": "Brief explanation of why this department"
}}

Rules:
- confidence should be 0.0-1.0 (0.8+ for clear matches, 0.5-0.8 for uncertain, <0.5 for unclear)
- If unclear, respond with "Unknown" and low confidence
- Consider the full conversation context, not just the last message
"""

        try:
            # Call Claude for analysis
            agent = ClaudeAgent(model='claude-3-haiku-20240307')
            response = agent.get_completion(prompt, conversation_history=[])

            # Parse JSON response
            import json
            result = json.loads(response)

            dept_name = result['department']
            if dept_name == 'Unknown':
                return None

            # Find department in database
            session = get_session()
            dept = session.query(Department).filter_by(name=dept_name, active=True).first()
            session.close()

            if not dept:
                return None

            return RoutingDecision(
                department=dept.name,
                department_id=dept.id,
                phone_number=dept.phone_number,
                method='ai_analysis',
                confidence=float(result['confidence']),
                reason=result['reasoning'],
                needs_confirmation=(float(result['confidence']) < 0.9)  # Confirm if < 90%
            )

        except Exception as e:
            print(f"[RoutingEngine] AI analysis error: {e}")
            return None

    def present_menu(self) -> RoutingDecision:
        """
        Return a menu presentation decision
        This triggers the AI to read out department options
        """
        return RoutingDecision(
            department='MENU',
            department_id=0,
            phone_number='',
            method='menu_selection',
            confidence=1.0,
            reason='Presenting menu options to caller',
            needs_confirmation=False
        )

    def get_default_route(self) -> RoutingDecision:
        """Default route when nothing else matches (usually Sales)"""
        session = get_session()
        dept = session.query(Department).filter_by(name='Sales', active=True).first()
        session.close()

        if dept:
            return RoutingDecision(
                department=dept.name,
                department_id=dept.id,
                phone_number=dept.phone_number,
                method='default',
                confidence=0.5,
                reason='Default routing (no clear match)',
                needs_confirmation=True
            )

        # Ultimate fallback
        return RoutingDecision(
            department='General',
            department_id=0,
            phone_number='+18166741783',
            method='default',
            confidence=0.5,
            reason='System default',
            needs_confirmation=True
        )

    def _format_history(self, history: list) -> str:
        """Format conversation history for AI prompt"""
        formatted = []
        for msg in history[-5:]:  # Last 5 messages
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            formatted.append(f"{role.title()}: {content}")
        return "\n".join(formatted)
```

#### C. Comment Out Detergent Workflow

**Modify: `app.py`**

Wrap lines ~920-1500 (detergent order collection logic):

```python
# ==============================================================================
# LEGACY: DETERGENT ORDERING WORKFLOW
# Status: DISABLED - Preserved for reference
# Date Disabled: 2025-11-05
# Reason: System converted to call routing (see CALL_ROUTING_TRANSFORMATION_PLAN.md)
# ==============================================================================

DETERGENT_WORKFLOW_ENABLED = False  # Set to True to re-enable

if DETERGENT_WORKFLOW_ENABLED:
    # ... all existing detergent code here ...

    # Detergent intent detection (line ~920)
    detergent_order_detected = detect_detergent_intent(user_text)
    if detergent_order_detected:
        # ... original workflow ...
        pass

    # Customer info collection (line ~1088)
    if conv_mgr.collecting_detergent_info:
        # ... all the phone/address/payment collection ...
        pass

# ==============================================================================
# END LEGACY CODE
# ==============================================================================
```

Keep these files unchanged:
- `quickbooks_client.py` - Intact, may be useful for future features
- `config.py` - Keep all QuickBooks config (just unused)

#### D. Implement New Routing Workflow

**Modify: `app.py` `generate_ai_response()` function**

Replace detergent logic with routing logic:

```python
async def generate_ai_response(call_sid: str, user_text: str, conv_mgr, session_info: dict):
    """Generate AI response with routing logic"""

    # Check if we need to route the call
    if not conv_mgr.routing_decision_made:
        print(f"[AI] Analyzing routing intent...")

        # Use routing engine
        from routing_engine import RoutingEngine
        engine = RoutingEngine()

        decision = engine.determine_route(user_text, conv_mgr.get_conversation_history())

        if decision.department == 'MENU':
            # Present menu
            menu_text = "I can connect you to:\n"
            menu_text += "Say 'Sales' for new orders and product information.\n"
            menu_text += "Say 'Support' for technical help.\n"
            menu_text += "Say 'Billing' for payment questions.\n"
            menu_text += "Which department can I connect you to?"

            return menu_text

        elif decision.needs_confirmation:
            # Ask for confirmation before routing
            conv_mgr.routing_department = decision.department
            conv_mgr.routing_confidence = decision.confidence
            conv_mgr.awaiting_routing_confirmation = True

            return f"I'll connect you to our {decision.department} team. Does that sound right?"

        else:
            # High confidence - route immediately
            conv_mgr.routing_decision_made = True
            conv_mgr.routing_department = decision.department
            conv_mgr.routing_confidence = decision.confidence
            conv_mgr.routing_method = decision.method

            # Initiate transfer
            await initiate_transfer(call_sid, decision)

            return f"Perfect! Connecting you to {decision.department} now..."

    elif conv_mgr.awaiting_routing_confirmation:
        # User responding to confirmation question
        user_response = user_text.lower()

        if any(word in user_response for word in ['yes', 'yeah', 'yep', 'correct', 'right', 'sure']):
            # Confirmed - proceed with routing
            conv_mgr.routing_decision_made = True

            # Get department info and transfer
            session = get_session()
            dept = session.query(Department).filter_by(name=conv_mgr.routing_department).first()
            session.close()

            decision = RoutingDecision(
                department=dept.name,
                department_id=dept.id,
                phone_number=dept.phone_number,
                method=conv_mgr.routing_method or 'confirmed',
                confidence=conv_mgr.routing_confidence,
                reason='User confirmed routing decision',
                needs_confirmation=False
            )

            await initiate_transfer(call_sid, decision)
            return f"Great! Connecting you to {dept.name} now..."

        else:
            # User said no - ask again
            conv_mgr.awaiting_routing_confirmation = False
            return "My apologies. How can I help you today?"

    else:
        # Already routed - this shouldn't happen
        # But handle gracefully
        return "I've connected you to the right team. They'll be with you shortly."


async def initiate_transfer(call_sid: str, decision: RoutingDecision):
    """Dial agent into conference"""
    import requests

    # Call the /dial-agent endpoint
    response = requests.post(f"{Config.BASE_URL}/dial-agent", json={
        'call_sid': call_sid,
        'department': decision.department,
        'agent_phone': decision.phone_number
    })

    if response.status_code == 200:
        print(f"[Routing] ✓ Transfer initiated to {decision.department}")

        # Log routing decision to database
        from database import create_call_route
        create_call_route({
            'call_sid': call_sid,
            'routing_decision': decision.department,
            'routing_method': decision.method,
            'routing_reason': decision.reason,
            'confidence_score': decision.confidence,
            'routed_to': decision.phone_number,
            'department_id': decision.department_id,
            'routed_at': datetime.utcnow()
        })
    else:
        print(f"[Routing] ❌ Transfer failed: {response.text}")
```

#### Testing Phase 3:
- [ ] Call system and say "I want to place an order"
- [ ] Verify keyword routing to Sales
- [ ] Call and say unclear phrase, verify menu presented
- [ ] Say "Sales" after menu, verify correct routing
- [ ] Check database `call_routes` table has routing decision logged
- [ ] Verify agent receives call in conference

---

### **PHASE 4: Enhanced Transcription** 📝

**Goal**: Continue transcription during human conversation and identify speakers

#### A. Update Transcript Callback

**Modify: `app.py` `deepgram_worker()` function**

**Current callback (~line 1715):**
```python
def on_transcript_callback(text, is_final):
    # Simple caller-only logic
    call_manager.add_transcript(call_sid, text, is_final, speaker='Caller')
    conv_mgr.add_transcript(text, is_final)
```

**New callback with speaker identification:**
```python
def on_transcript_callback(text, is_final):
    """
    Enhanced transcript callback with speaker identification
    Stores transcripts in database instead of files
    """
    conv_mgr = conversation_managers.get(call_sid)
    if not conv_mgr:
        return

    # Determine speaker based on call state
    speaker = identify_speaker(call_sid, text, is_final, conv_mgr)

    # Store in database (replaces file storage)
    from database import create_transcript
    create_transcript(
        call_sid=call_sid,
        speaker=speaker,
        text=text,
        is_final=is_final,
        confidence=None  # Could extract from Deepgram metadata
    )

    # Still update conversation manager for routing logic
    if speaker == 'caller' and conv_mgr.state != ConversationState.HUMAN_CONVERSATION:
        conv_mgr.add_transcript(text, is_final)

    # Log for monitoring
    if is_final:
        print(f"[Transcript] {speaker}: {text}")


def identify_speaker(call_sid: str, text: str, is_final: bool, conv_mgr) -> str:
    """
    Identify who is speaking: caller, agent, or AI

    Uses heuristics based on:
    - Call state (before/after transfer)
    - Timing (did agent recently join?)
    - Text patterns (AI responses are known)
    """

    # Before transfer: Only caller speaks (AI uses TTS, not in stream)
    if conv_mgr.state in [ConversationState.GREETING,
                          ConversationState.ROUTING_QUESTION,
                          ConversationState.ANALYZING_INTENT]:
        return 'caller'

    # During transfer: Could be caller or agent
    if conv_mgr.state == ConversationState.HUMAN_CONVERSATION:
        # Check if agent recently joined (first 10 seconds likely agent intro)
        if conv_mgr.agent_joined_at:
            time_since_join = (datetime.utcnow() - conv_mgr.agent_joined_at).total_seconds()

            if time_since_join < 10:
                # First few seconds after join = likely agent
                # Look for agent greeting patterns
                agent_greetings = ['hello', 'hi', 'thanks for holding', 'this is',
                                  'how can i help', 'what can i do']
                if any(phrase in text.lower() for phrase in agent_greetings):
                    return 'agent'

        # Advanced: Could implement speaker diarization here
        # For now, use simple alternating logic
        # (Get last speaker from database)
        from database import get_session, CallTranscript
        session = get_session()
        last_transcript = session.query(CallTranscript).filter_by(
            call_sid=call_sid,
            is_final=True
        ).order_by(CallTranscript.timestamp.desc()).first()
        session.close()

        if last_transcript:
            # Alternate between caller and agent
            return 'agent' if last_transcript.speaker == 'caller' else 'caller'

        # Default: assume caller
        return 'caller'

    # Default
    return 'caller'
```

#### B. Update ConversationManager

**Modify: `conversation_manager.py`**

Add agent tracking:
```python
def mark_agent_joined(self):
    """Called when agent joins conference"""
    self.agent_joined_at = datetime.utcnow()
    self.state = ConversationState.HUMAN_CONVERSATION
    print(f"[ConversationManager] Agent joined, state: HUMAN_CONVERSATION")
```

**Call this from `/conference-status` webhook:**
```python
# In app.py /conference-status
if event == 'participant-join':
    participant_label = request.form.get('ParticipantLabel')

    # If this is the second participant (agent), mark it
    conf_info = conference_manager.get_conference_info(call_sid)
    if conf_info and len(conf_info['participants']) == 1:  # Agent is 2nd
        conv_mgr = conversation_managers.get(call_sid)
        if conv_mgr:
            conv_mgr.mark_agent_joined()
```

#### C. Replace File-Based Transcript Storage

**Modify: `call_manager.py`**

**Old approach (~line 70):**
```python
def save_transcript(self, call_sid):
    """Save to transcripts/{timestamp}.txt file"""
    # ... writes to file ...
```

**New approach:**
```python
def save_transcript(self, call_sid):
    """
    Transcripts now stored in database in real-time
    This function generates a final summary and exports if needed
    """
    from database import get_session, CallTranscript

    session = get_session()
    transcripts = session.query(CallTranscript).filter_by(
        call_sid=call_sid,
        is_final=True
    ).order_by(CallTranscript.timestamp).all()
    session.close()

    if not transcripts:
        print(f"[CallManager] No transcripts found for {call_sid}")
        return

    # Optional: Export to file as backup
    if Config.EXPORT_TRANSCRIPTS_TO_FILES:
        filename = f"transcripts/{call_sid}.txt"
        with open(filename, 'w') as f:
            f.write(f"Call SID: {call_sid}\n")
            f.write(f"Transcript ({len(transcripts)} segments)\n\n")

            for t in transcripts:
                timestamp = t.timestamp.strftime("%H:%M:%S")
                f.write(f"[{timestamp}] {t.speaker}: {t.text}\n")

        print(f"[CallManager] Exported transcript to {filename}")

    # Generate AI summary (optional - can be async job)
    if Config.GENERATE_CALL_SUMMARIES:
        summary = self._generate_summary(transcripts)
        self._update_call_metadata(call_sid, summary)


def _generate_summary(self, transcripts: list) -> str:
    """Use Claude to generate conversation summary"""
    from claude_agent import ClaudeAgent

    # Build transcript text
    transcript_text = "\n".join([
        f"{t.speaker}: {t.text}" for t in transcripts
    ])

    prompt = f"""Summarize this customer service call in 2-3 sentences:

{transcript_text}

Summary:"""

    agent = ClaudeAgent(model='claude-3-haiku-20240307')
    summary = agent.get_completion(prompt, [])

    return summary
```

#### D. Optional: Upgrade to Deepgram Speaker Diarization

**Modify: `app.py` Deepgram connection**

**Current config (~line 1620):**
```python
options = LiveOptions(
    model="nova-2",
    encoding="mulaw",
    sample_rate=8000,
    channels=1,
    punctuate=True,
    interim_results=True
)
```

**With diarization (requires Deepgram paid plan):**
```python
options = LiveOptions(
    model="nova-2",
    encoding="mulaw",
    sample_rate=8000,
    channels=1,
    punctuate=True,
    interim_results=True,
    diarize=True,  # Enable speaker diarization
    diarize_version="2021-07-14"
)

# Then in callback, check for speaker info:
def on_message(self, result, **kwargs):
    sentence = result.channel.alternatives[0].transcript
    is_final = result.is_final

    # NEW: Get speaker info
    speaker_num = result.channel.alternatives[0].words[0].speaker if result.channel.alternatives[0].words else None

    # Map speaker numbers to labels
    speaker_label = 'caller' if speaker_num == 0 else 'agent'
```

#### Testing Phase 4:
- [ ] Make test call, route to human
- [ ] After human answers, speak as caller
- [ ] Have human agent respond
- [ ] Check database `call_transcripts` table
- [ ] Verify speaker labels correct (caller vs agent)
- [ ] View full transcript in database
- [ ] Optional: Test AI summary generation

---

### **PHASE 5: Admin Dashboard** 🎛️

**Goal**: Web interface to manage routing without code changes

#### A. Create Admin Routes

**Create: `admin_routes.py`** (NEW FILE)

```python
"""
Admin API Routes - Manage departments and routing rules
"""
from flask import Blueprint, request, jsonify, render_template
from functools import wraps
from database import get_session, Department, RoutingRule, CallRoute, CallTranscript
from config import Config

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# Simple auth decorator
def require_admin_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.password != Config.ADMIN_PASSWORD:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


# ==================== DEPARTMENT MANAGEMENT ====================

@admin_bp.route('/departments', methods=['GET'])
@require_admin_auth
def list_departments():
    """GET /admin/departments - List all departments"""
    session = get_session()
    departments = session.query(Department).order_by(Department.priority.desc()).all()
    session.close()

    return jsonify([{
        'id': d.id,
        'name': d.name,
        'phone_number': d.phone_number,
        'description': d.description,
        'active': d.active,
        'priority': d.priority
    } for d in departments])


@admin_bp.route('/departments', methods=['POST'])
@require_admin_auth
def create_department():
    """POST /admin/departments - Create new department"""
    data = request.json

    session = get_session()
    dept = Department(
        name=data['name'],
        phone_number=data['phone_number'],
        description=data.get('description', ''),
        priority=data.get('priority', 0),
        active=data.get('active', True)
    )
    session.add(dept)
    session.commit()
    dept_id = dept.id
    session.close()

    return jsonify({'id': dept_id, 'message': 'Department created'}), 201


@admin_bp.route('/departments/<int:dept_id>', methods=['PUT'])
@require_admin_auth
def update_department(dept_id):
    """PUT /admin/departments/<id> - Update department"""
    data = request.json

    session = get_session()
    dept = session.query(Department).get(dept_id)

    if not dept:
        session.close()
        return jsonify({'error': 'Department not found'}), 404

    if 'name' in data:
        dept.name = data['name']
    if 'phone_number' in data:
        dept.phone_number = data['phone_number']
    if 'description' in data:
        dept.description = data['description']
    if 'active' in data:
        dept.active = data['active']
    if 'priority' in data:
        dept.priority = data['priority']

    session.commit()
    session.close()

    return jsonify({'message': 'Department updated'})


# ==================== ROUTING RULES ====================

@admin_bp.route('/routing-rules', methods=['GET'])
@require_admin_auth
def list_routing_rules():
    """GET /admin/routing-rules - List all rules"""
    session = get_session()
    rules = session.query(RoutingRule).order_by(RoutingRule.priority.desc()).all()
    session.close()

    return jsonify([{
        'id': r.id,
        'rule_name': r.rule_name,
        'keywords': r.keywords,
        'department': r.department.name,
        'department_id': r.department_id,
        'priority': r.priority,
        'active': r.active,
        'match_type': r.match_type
    } for r in rules])


@admin_bp.route('/routing-rules', methods=['POST'])
@require_admin_auth
def create_routing_rule():
    """POST /admin/routing-rules - Create new rule"""
    data = request.json

    session = get_session()
    rule = RoutingRule(
        rule_name=data['rule_name'],
        keywords=data['keywords'],  # Array of strings
        department_id=data['department_id'],
        priority=data.get('priority', 0),
        active=data.get('active', True),
        match_type=data.get('match_type', 'any')
    )
    session.add(rule)
    session.commit()
    rule_id = rule.id
    session.close()

    return jsonify({'id': rule_id, 'message': 'Routing rule created'}), 201


@admin_bp.route('/routing-rules/<int:rule_id>', methods=['PUT'])
@require_admin_auth
def update_routing_rule(rule_id):
    """PUT /admin/routing-rules/<id> - Update rule"""
    data = request.json

    session = get_session()
    rule = session.query(RoutingRule).get(rule_id)

    if not rule:
        session.close()
        return jsonify({'error': 'Rule not found'}), 404

    if 'rule_name' in data:
        rule.rule_name = data['rule_name']
    if 'keywords' in data:
        rule.keywords = data['keywords']
    if 'department_id' in data:
        rule.department_id = data['department_id']
    if 'priority' in data:
        rule.priority = data['priority']
    if 'active' in data:
        rule.active = data['active']
    if 'match_type' in data:
        rule.match_type = data['match_type']

    session.commit()
    session.close()

    return jsonify({'message': 'Rule updated'})


@admin_bp.route('/routing-rules/<int:rule_id>', methods=['DELETE'])
@require_admin_auth
def delete_routing_rule(rule_id):
    """DELETE /admin/routing-rules/<id> - Deactivate rule"""
    session = get_session()
    rule = session.query(RoutingRule).get(rule_id)

    if not rule:
        session.close()
        return jsonify({'error': 'Rule not found'}), 404

    rule.active = False
    session.commit()
    session.close()

    return jsonify({'message': 'Rule deactivated'})


# ==================== CALL HISTORY ====================

@admin_bp.route('/calls', methods=['GET'])
@require_admin_auth
def list_calls():
    """GET /admin/calls - List recent calls with routing info"""
    limit = request.args.get('limit', 50, type=int)

    session = get_session()
    calls = session.query(CallRoute).order_by(
        CallRoute.created_at.desc()
    ).limit(limit).all()
    session.close()

    return jsonify([{
        'call_sid': c.call_sid,
        'caller_phone': c.caller_phone,
        'department': c.routing_decision,
        'method': c.routing_method,
        'confidence': float(c.confidence_score) if c.confidence_score else None,
        'routed_at': c.routed_at.isoformat() if c.routed_at else None,
        'duration': c.call_duration_seconds
    } for c in calls])


@admin_bp.route('/calls/<call_sid>', methods=['GET'])
@require_admin_auth
def get_call_details(call_sid):
    """GET /admin/calls/<call_sid> - Full transcript and routing details"""
    session = get_session()

    # Get routing info
    route = session.query(CallRoute).filter_by(call_sid=call_sid).first()

    # Get transcript
    transcripts = session.query(CallTranscript).filter_by(
        call_sid=call_sid,
        is_final=True
    ).order_by(CallTranscript.timestamp).all()

    session.close()

    if not route:
        return jsonify({'error': 'Call not found'}), 404

    return jsonify({
        'call_sid': call_sid,
        'caller_phone': route.caller_phone,
        'department': route.routing_decision,
        'method': route.routing_method,
        'reason': route.routing_reason,
        'confidence': float(route.confidence_score) if route.confidence_score else None,
        'routed_at': route.routed_at.isoformat() if route.routed_at else None,
        'duration': route.call_duration_seconds,
        'transcript': [{
            'timestamp': t.timestamp.isoformat(),
            'speaker': t.speaker,
            'text': t.text
        } for t in transcripts]
    })


# ==================== ANALYTICS ====================

@admin_bp.route('/analytics', methods=['GET'])
@require_admin_auth
def get_analytics():
    """GET /admin/analytics - Dashboard metrics"""
    from sqlalchemy import func

    session = get_session()

    # Calls per department (last 30 days)
    dept_stats = session.query(
        CallRoute.routing_decision,
        func.count(CallRoute.id).label('count')
    ).filter(
        CallRoute.created_at >= datetime.utcnow() - timedelta(days=30)
    ).group_by(CallRoute.routing_decision).all()

    # Average call duration
    avg_duration = session.query(
        func.avg(CallRoute.call_duration_seconds)
    ).scalar()

    # Routing method breakdown
    method_stats = session.query(
        CallRoute.routing_method,
        func.count(CallRoute.id).label('count')
    ).group_by(CallRoute.routing_method).all()

    session.close()

    return jsonify({
        'calls_per_department': [{'department': d, 'count': c} for d, c in dept_stats],
        'avg_call_duration_seconds': float(avg_duration) if avg_duration else 0,
        'routing_methods': [{'method': m, 'count': c} for m, c in method_stats]
    })


# ==================== TEST ROUTING ====================

@admin_bp.route('/test-route', methods=['POST'])
@require_admin_auth
def test_routing():
    """POST /admin/test-route - Test routing engine with sample text"""
    data = request.json
    text = data.get('text', '')

    if not text:
        return jsonify({'error': 'Text required'}), 400

    from routing_engine import RoutingEngine
    engine = RoutingEngine()

    decision = engine.determine_route(text, [])

    return jsonify({
        'input': text,
        'department': decision.department,
        'method': decision.method,
        'confidence': decision.confidence,
        'reason': decision.reason,
        'needs_confirmation': decision.needs_confirmation
    })
```

#### B. Register Admin Blueprint

**Modify: `app.py`**

```python
# At top of file
from admin_routes import admin_bp

# After app initialization
app.register_blueprint(admin_bp)
```

#### C. Add Admin Config

**Modify: `config.py`**

```python
# Admin interface settings
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'changeme123')
ADMIN_ENABLED = os.getenv('ADMIN_ENABLED', 'true').lower() == 'true'
```

**Add to `.env`:**
```bash
ADMIN_PASSWORD=your-secure-password-here
ADMIN_ENABLED=true
```

#### D. Create Simple HTML Dashboard (Optional)

**Create: `templates/admin/dashboard.html`**

```html
<!DOCTYPE html>
<html>
<head>
    <title>Call Routing Admin</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .section { margin-bottom: 40px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #4CAF50; color: white; }
        button { padding: 5px 10px; cursor: pointer; }
        .add-btn { background-color: #4CAF50; color: white; border: none; }
        .edit-btn { background-color: #2196F3; color: white; border: none; }
        .delete-btn { background-color: #f44336; color: white; border: none; }
    </style>
</head>
<body>
    <h1>Call Routing Admin Dashboard</h1>

    <!-- Departments Section -->
    <div class="section">
        <h2>Departments</h2>
        <button class="add-btn" onclick="addDepartment()">+ Add Department</button>
        <table id="departments-table">
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Phone Number</th>
                    <th>Description</th>
                    <th>Active</th>
                    <th>Priority</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="departments-body">
                <!-- Populated by JavaScript -->
            </tbody>
        </table>
    </div>

    <!-- Routing Rules Section -->
    <div class="section">
        <h2>Routing Rules</h2>
        <button class="add-btn" onclick="addRule()">+ Add Rule</button>
        <table id="rules-table">
            <thead>
                <tr>
                    <th>Rule Name</th>
                    <th>Keywords</th>
                    <th>Department</th>
                    <th>Priority</th>
                    <th>Active</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="rules-body">
                <!-- Populated by JavaScript -->
            </tbody>
        </table>
    </div>

    <!-- Recent Calls Section -->
    <div class="section">
        <h2>Recent Calls</h2>
        <table id="calls-table">
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Caller</th>
                    <th>Department</th>
                    <th>Method</th>
                    <th>Confidence</th>
                    <th>Duration</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="calls-body">
                <!-- Populated by JavaScript -->
            </tbody>
        </table>
    </div>

    <script>
        // Basic auth header
        const auth = btoa('admin:' + prompt('Enter admin password:'));
        const headers = {
            'Authorization': 'Basic ' + auth,
            'Content-Type': 'application/json'
        };

        // Load data
        async function loadDepartments() {
            const response = await fetch('/admin/departments', { headers });
            const data = await response.json();

            const tbody = document.getElementById('departments-body');
            tbody.innerHTML = data.map(d => `
                <tr>
                    <td>${d.name}</td>
                    <td>${d.phone_number}</td>
                    <td>${d.description}</td>
                    <td>${d.active ? '✓' : '✗'}</td>
                    <td>${d.priority}</td>
                    <td>
                        <button class="edit-btn" onclick="editDepartment(${d.id})">Edit</button>
                    </td>
                </tr>
            `).join('');
        }

        async function loadRules() {
            const response = await fetch('/admin/routing-rules', { headers });
            const data = await response.json();

            const tbody = document.getElementById('rules-body');
            tbody.innerHTML = data.map(r => `
                <tr>
                    <td>${r.rule_name}</td>
                    <td>${r.keywords.join(', ')}</td>
                    <td>${r.department}</td>
                    <td>${r.priority}</td>
                    <td>${r.active ? '✓' : '✗'}</td>
                    <td>
                        <button class="edit-btn" onclick="editRule(${r.id})">Edit</button>
                        <button class="delete-btn" onclick="deleteRule(${r.id})">Delete</button>
                    </td>
                </tr>
            `).join('');
        }

        async function loadCalls() {
            const response = await fetch('/admin/calls?limit=20', { headers });
            const data = await response.json();

            const tbody = document.getElementById('calls-body');
            tbody.innerHTML = data.map(c => `
                <tr>
                    <td>${new Date(c.routed_at).toLocaleString()}</td>
                    <td>${c.caller_phone}</td>
                    <td>${c.department}</td>
                    <td>${c.method}</td>
                    <td>${c.confidence ? (c.confidence * 100).toFixed(0) + '%' : '-'}</td>
                    <td>${c.duration ? c.duration + 's' : '-'}</td>
                    <td>
                        <button class="edit-btn" onclick="viewTranscript('${c.call_sid}')">View</button>
                    </td>
                </tr>
            `).join('');
        }

        function viewTranscript(call_sid) {
            window.open('/admin/calls/' + call_sid, '_blank');
        }

        // Load on page load
        loadDepartments();
        loadRules();
        loadCalls();
    </script>
</body>
</html>
```

**Add route to serve dashboard:**
```python
@app.route('/admin/dashboard')
def admin_dashboard():
    return render_template('admin/dashboard.html')
```

#### Testing Phase 5:
- [ ] Access `/admin/dashboard` in browser
- [ ] Authenticate with admin password
- [ ] View list of departments
- [ ] Add new department (e.g., "Accounting")
- [ ] Edit department phone number
- [ ] Create new routing rule with keywords
- [ ] Test routing with `/admin/test-route` endpoint
- [ ] View recent calls list
- [ ] Click on call to see full transcript
- [ ] Verify changes take effect immediately (no deployment needed)

---

## 📊 Implementation Timeline

**Estimated Timeline: 5 Weeks (Full-Time) or 10 Weeks (Part-Time)**

| Week | Phase | Key Deliverables | Hours |
|------|-------|------------------|-------|
| 1 | Phase 1 | Conference architecture working, transcription continues | 30-40 |
| 2 | Phase 2 | Database tables created, migrations run successfully | 20-30 |
| 3 | Phase 3 | Routing engine working, detergent code disabled | 30-40 |
| 4 | Phase 4 | Speaker identification, transcript storage in DB | 20-30 |
| 5 | Phase 5 | Admin dashboard operational | 20-30 |

**Total Estimated Hours:** 120-170 hours

---

## 🔧 Configuration Changes

**Add to `.env`:**
```bash
# Conference settings
CONFERENCE_WAIT_URL=http://twimlets.com/holdmusic?Bucket=com.twilio.music.classical
CONFERENCE_STATUS_CALLBACK_URL=https://your-server.com/conference-status
CONFERENCE_RECORD=true

# Admin interface
ADMIN_PASSWORD=your-secure-password
ADMIN_ENABLED=true

# Routing
AI_ROUTING_CONFIDENCE_THRESHOLD=0.8
MENU_FALLBACK_ENABLED=true
DEFAULT_ROUTING_TIMEOUT=30

# Transcript export
EXPORT_TRANSCRIPTS_TO_FILES=false
GENERATE_CALL_SUMMARIES=true

# Legacy (disable detergent workflow)
DETERGENT_WORKFLOW_ENABLED=false
```

---

## 🧪 Testing Checklist

### Phase 1: Conference Architecture
- [ ] Incoming call creates conference room
- [ ] Media Stream stays active
- [ ] Can dial agent into conference programmatically
- [ ] Deepgram captures both caller and agent audio
- [ ] Conference events logged correctly

### Phase 2: Database
- [ ] Migration script runs without errors
- [ ] All 5 tables created successfully
- [ ] Can insert/query departments via SQLAlchemy
- [ ] Can insert/query routing rules
- [ ] Foreign keys work correctly

### Phase 3: Routing Logic
- [ ] Keyword "order" routes to Sales
- [ ] Keyword "problem" routes to Support
- [ ] Unclear phrase triggers menu
- [ ] Menu selection routes correctly
- [ ] AI analysis works for complex requests
- [ ] Routing decision logged in database
- [ ] Agent receives call in conference

### Phase 4: Transcription
- [ ] Transcripts stored in database during call
- [ ] Speaker labels correct (caller/agent)
- [ ] Both speakers captured after transfer
- [ ] Can query full conversation from database
- [ ] AI summary generates correctly

### Phase 5: Admin Dashboard
- [ ] Can access dashboard with password
- [ ] Department CRUD operations work
- [ ] Routing rule CRUD operations work
- [ ] Changes take effect immediately
- [ ] Can view call history
- [ ] Can view individual transcripts
- [ ] Analytics display correctly

---

## 🚨 Rollback Plan

If issues arise during implementation:

1. **Emergency Revert (< 5 minutes):**
   ```python
   # In app.py, line ~500
   # Comment out conference code, restore original:
   response.pause(length=600)

   # In app.py, set:
   DETERGENT_WORKFLOW_ENABLED = True
   ```

2. **Database Rollback:**
   ```bash
   # Restore from backup
   pg_restore -d phone_agent backup.sql

   # Or drop new tables
   DROP TABLE call_transcripts;
   DROP TABLE call_routes;
   DROP TABLE routing_rules;
   DROP TABLE departments;
   DROP TABLE calls_metadata;
   ```

3. **Gradual Rollback:**
   - Keep conference architecture (it's better)
   - Disable routing logic
   - Keep using detergent workflow

---

## 💰 Cost Impact Analysis

### Twilio Conference Costs
- **Current:** `$0.0130/min` per call (Media Streams)
- **New:** `$0.0130/min + $0.0025/min × 2 participants = $0.018/min`
- **Increase:** +38% per call (+$0.005/min)
- **Monthly Impact:** 1000 calls × 5 min avg = +$25/month

### Deepgram Costs
- **No change** for basic transcription
- **Optional Diarization:** +$0.0005/min (+$2.50/month for 1000 calls)

### Database Storage
- **Transcripts:** ~1-2 KB per minute of speech
- **1000 calls × 5 min × 2 KB = 10 MB/month** (negligible)

### Total Additional Cost
- **~$25-30/month** for 1000 calls/month average
- **ROI:** Immediate - enables human agent involvement + full conversation logs

---

## 📚 Documentation Files to Create

1. **This file:** `CALL_ROUTING_TRANSFORMATION_PLAN.md`
2. **Database Schema:** `docs/database_schema.md`
3. **API Documentation:** `docs/admin_api.md`
4. **Routing Rules Guide:** `docs/routing_configuration.md`
5. **Deployment Guide:** `docs/deployment.md`

---

## ✅ Success Criteria

**Phase 1 Complete When:**
- [ ] Call transfers to human without losing transcription
- [ ] Both speakers audible in recording
- [ ] Conference events logged

**Phase 2 Complete When:**
- [ ] All tables created with migrations
- [ ] Can query/insert via SQLAlchemy
- [ ] Sample data exists for testing

**Phase 3 Complete When:**
- [ ] Routing works for all three methods (AI/keyword/menu)
- [ ] Detergent code disabled but preserved
- [ ] Routing decisions logged

**Phase 4 Complete When:**
- [ ] Transcripts stored in DB during call
- [ ] Speaker identification > 80% accurate
- [ ] Can export full conversation

**Phase 5 Complete When:**
- [ ] Admin dashboard accessible
- [ ] Can modify routing rules without code deploy
- [ ] Changes take effect immediately

---

## 🎯 Next Steps

1. **Review this plan** with stakeholders
2. **Set up development environment** (separate from production)
3. **Create database backup** before migrations
4. **Start with Phase 1** (conference architecture)
5. **Test thoroughly** at each phase
6. **Deploy to production** after Phase 3 minimum

---

**Document Version:** 1.0
**Last Updated:** 2025-11-05
**Author:** Claude (Anthropic)
**Status:** Ready for Implementation