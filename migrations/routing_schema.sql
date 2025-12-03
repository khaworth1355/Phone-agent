-- Call Routing Schema Migration
-- Creates tables for call routing system
-- Run once with: python migrations/add_routing_schema.py

-- ==================== DEPARTMENTS ====================
CREATE TABLE IF NOT EXISTS departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    description TEXT,
    active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Seed initial departments
INSERT INTO departments (name, phone_number, description, priority) VALUES
    ('Sales', '+18166741783', 'New orders, product inquiries, and account upgrades', 1),
    ('Support', '+18166741783', 'Technical issues, troubleshooting, and customer support', 2),
    ('Billing', '+18166741783', 'Billing questions, payment issues, and account management', 3)
ON CONFLICT (name) DO NOTHING;


-- ==================== ROUTING RULES ====================
CREATE TABLE IF NOT EXISTS routing_rules (
    id SERIAL PRIMARY KEY,
    rule_name VARCHAR(100) NOT NULL,
    keywords TEXT[] NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    priority INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    match_type VARCHAR(20) DEFAULT 'any',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Seed initial routing rules
INSERT INTO routing_rules (rule_name, keywords, department_id, priority, match_type) VALUES
    ('Order Keywords', ARRAY['order', 'purchase', 'buy', 'detergent', 'place order', 'want to order', 'need to order'], (SELECT id FROM departments WHERE name = 'Sales'), 100, 'any'),
    ('Support Issues', ARRAY['problem', 'issue', 'broken', 'not working', 'help', 'error', 'malfunction', 'fix'], (SELECT id FROM departments WHERE name = 'Support'), 90, 'any'),
    ('Billing Questions', ARRAY['bill', 'billing', 'charge', 'payment', 'invoice', 'account', 'paid', 'owe'], (SELECT id FROM departments WHERE name = 'Billing'), 80, 'any')
ON CONFLICT DO NOTHING;


-- ==================== CALL ROUTES ====================
CREATE TABLE IF NOT EXISTS call_routes (
    id SERIAL PRIMARY KEY,
    call_sid VARCHAR(100) NOT NULL UNIQUE,
    caller_phone VARCHAR(50),
    routing_decision VARCHAR(100),
    routing_method VARCHAR(50),
    routing_reason TEXT,
    confidence_score NUMERIC(3,2),
    routed_to VARCHAR(100),
    department_id INTEGER REFERENCES departments(id),
    routed_at TIMESTAMP,
    agent_answered_at TIMESTAMP,
    call_ended_at TIMESTAMP,
    call_duration_seconds INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_call_routes_call_sid ON call_routes(call_sid);
CREATE INDEX IF NOT EXISTS idx_call_routes_department ON call_routes(department_id);
CREATE INDEX IF NOT EXISTS idx_call_routes_created_at ON call_routes(created_at);


-- ==================== CALL TRANSCRIPTS ====================
CREATE TABLE IF NOT EXISTS call_transcripts (
    id SERIAL PRIMARY KEY,
    call_sid VARCHAR(100) NOT NULL,
    speaker VARCHAR(20) NOT NULL,
    text TEXT NOT NULL,
    is_final BOOLEAN DEFAULT FALSE,
    confidence NUMERIC(3,2),
    timestamp TIMESTAMP DEFAULT NOW(),
    segment_number INTEGER,

    CONSTRAINT check_speaker CHECK (speaker IN ('caller', 'agent', 'ai'))
);

CREATE INDEX IF NOT EXISTS idx_transcripts_call_sid ON call_transcripts(call_sid);
CREATE INDEX IF NOT EXISTS idx_transcripts_timestamp ON call_transcripts(timestamp);
CREATE INDEX IF NOT EXISTS idx_transcripts_speaker ON call_transcripts(speaker);


-- ==================== CALL METADATA ====================
CREATE TABLE IF NOT EXISTS calls_metadata (
    call_sid VARCHAR(100) PRIMARY KEY,
    caller_phone VARCHAR(50),
    caller_name VARCHAR(200),
    routing_stage VARCHAR(50),
    conversation_summary TEXT,
    outcome VARCHAR(50),
    call_started_at TIMESTAMP,
    call_ended_at TIMESTAMP,
    total_duration_seconds INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
