# Database Schema Changes - Transcription Type Addition

**Date**: 2025-11-07
**Database**: PostgreSQL
**Version**: 1.1.0
**Migration File**: `migration_add_transcription_type.sql`

---

## Summary of Changes

Added `transcription_type` column to `call_transcripts` table to distinguish between:
- **`realtime`**: Transcripts generated during AI conversation (real-time streaming)
- **`batch`**: Transcripts generated post-call with speaker diarization (accurate speaker labels)

---

## Complete Database Schema

### Table: `detergent_orders`
Stores detergent orders placed via phone with QuickBooks integration.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | AUTO | Primary key |
| `call_sid` | VARCHAR(100) | NO | - | Twilio call SID |
| `customer_name` | VARCHAR(200) | NO | - | Customer full name |
| `customer_phone` | VARCHAR(50) | NO | - | Customer phone number |
| `customer_email` | VARCHAR(200) | YES | NULL | Customer email address |
| `address_street` | VARCHAR(300) | NO | - | Street address |
| `address_city` | VARCHAR(100) | NO | - | City |
| `address_state` | VARCHAR(50) | NO | - | State (full name or abbreviation) |
| `address_zip` | VARCHAR(10) | NO | - | ZIP code |
| `payment_method` | VARCHAR(100) | NO | - | Payment method (credit, check, invoice) |
| `quantity` | INTEGER | NO | 1 | Number of units ordered |
| `qb_customer_id` | VARCHAR(50) | YES | NULL | QuickBooks Customer ID |
| `qb_invoice_id` | VARCHAR(50) | YES | NULL | QuickBooks Invoice ID |
| `qb_invoice_number` | VARCHAR(50) | YES | NULL | QuickBooks Invoice Number |
| `sync_status` | VARCHAR(20) | NO | 'pending' | Sync status: pending, synced, failed |
| `sync_error` | TEXT | YES | NULL | Error message if sync failed |
| `created_at` | TIMESTAMP | NO | NOW() | Order creation timestamp |
| `synced_at` | TIMESTAMP | YES | NULL | QuickBooks sync timestamp |

---

### Table: `departments`
Defines routing departments (Sales, Support, Billing, etc.).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | AUTO | Primary key |
| `name` | VARCHAR(100) | NO | - | Department name (unique) |
| `phone_number` | VARCHAR(20) | NO | - | Destination phone number |
| `description` | TEXT | YES | NULL | Department description |
| `active` | BOOLEAN | NO | TRUE | Whether department is active |
| `priority` | INTEGER | NO | 0 | Display order (higher = first) |
| `created_at` | TIMESTAMP | NO | NOW() | Creation timestamp |
| `updated_at` | TIMESTAMP | NO | NOW() | Last update timestamp |

**Indexes**:
- `UNIQUE(name)`

---

### Table: `routing_rules`
Keyword-based routing rules to match caller intent to departments.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | AUTO | Primary key |
| `rule_name` | VARCHAR(100) | NO | - | Rule name for reference |
| `keywords` | TEXT[] | NO | - | PostgreSQL array of keywords |
| `department_id` | INTEGER | NO | FK | Foreign key to departments.id |
| `priority` | INTEGER | NO | 0 | Rule priority (higher checked first) |
| `active` | BOOLEAN | NO | TRUE | Whether rule is active |
| `match_type` | VARCHAR(20) | NO | 'any' | Match type: 'any' or 'all' |
| `created_at` | TIMESTAMP | NO | NOW() | Creation timestamp |
| `updated_at` | TIMESTAMP | NO | NOW() | Last update timestamp |

**Foreign Keys**:
- `department_id` → `departments.id`

**Indexes**:
- `INDEX(department_id)`
- `INDEX(priority)`

---

### Table: `call_routes`
Logs routing decisions and call outcomes.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | AUTO | Primary key |
| `call_sid` | VARCHAR(100) | NO | - | Twilio call SID (unique) |
| `caller_phone` | VARCHAR(50) | YES | NULL | Caller phone number |
| `routing_decision` | VARCHAR(100) | YES | NULL | Department name chosen |
| `routing_method` | VARCHAR(50) | YES | NULL | Method: ai_analysis, keyword_match, menu_selection |
| `routing_reason` | TEXT | YES | NULL | Explanation for routing decision |
| `confidence_score` | NUMERIC(3,2) | YES | NULL | AI confidence (0.00-1.00) |
| `routed_to` | VARCHAR(100) | YES | NULL | Agent phone number |
| `department_id` | INTEGER | YES | FK | Foreign key to departments.id |
| `routed_at` | TIMESTAMP | YES | NULL | When transfer was initiated |
| `agent_answered_at` | TIMESTAMP | YES | NULL | When agent joined conference |
| `call_ended_at` | TIMESTAMP | YES | NULL | When call disconnected |
| `call_duration_seconds` | INTEGER | YES | NULL | Total call duration |
| `created_at` | TIMESTAMP | NO | NOW() | Record creation timestamp |

**Foreign Keys**:
- `department_id` → `departments.id`

**Indexes**:
- `UNIQUE(call_sid)`
- `INDEX(department_id)`
- `INDEX(routed_at)`

---

### Table: `call_transcripts` ⭐ MODIFIED

Stores conversation transcripts with speaker labels.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NO | AUTO | Primary key |
| `call_sid` | VARCHAR(100) | NO | - | Twilio call SID |
| `speaker` | VARCHAR(20) | NO | - | Speaker: 'caller', 'agent', 'ai' |
| `text` | TEXT | NO | - | Transcript text |
| `is_final` | BOOLEAN | NO | FALSE | TRUE for final, FALSE for interim |
| `confidence` | NUMERIC(3,2) | YES | NULL | Deepgram confidence score |
| `timestamp` | TIMESTAMP | NO | NOW() | Transcript timestamp |
| `segment_number` | INTEGER | YES | NULL | Order in conversation |
| `transcription_type` | VARCHAR(20) | NO | 'realtime' | **NEW**: 'realtime' or 'batch' |

**🆕 New Column Details**:

- **Column**: `transcription_type`
- **Type**: `VARCHAR(20)`
- **Default**: `'realtime'`
- **Values**:
  - `'realtime'`: Generated during live AI conversation (may have inaccurate speaker labels)
  - `'batch'`: Generated post-call using Deepgram diarization (accurate speaker labels)

**Foreign Keys**: None

**Indexes**:
- `INDEX(call_sid)`
- `INDEX(segment_number)`
- `INDEX(transcription_type)` ← **NEW**

---

### Table: `calls_metadata`
Enhanced call tracking and summaries.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `call_sid` | VARCHAR(100) | NO | - | Twilio call SID (primary key) |
| `caller_phone` | VARCHAR(50) | YES | NULL | Caller phone number |
| `caller_name` | VARCHAR(200) | YES | NULL | Caller name (if recognized) |
| `routing_stage` | VARCHAR(50) | YES | NULL | Stage: greeting, routing, transferred, ended |
| `conversation_summary` | TEXT | YES | NULL | AI-generated summary |
| `outcome` | VARCHAR(50) | YES | NULL | Outcome: routed_successfully, no_answer, etc. |
| `call_started_at` | TIMESTAMP | YES | NULL | Call start time |
| `call_ended_at` | TIMESTAMP | YES | NULL | Call end time |
| `total_duration_seconds` | INTEGER | YES | NULL | Total call duration |
| `created_at` | TIMESTAMP | NO | NOW() | Record creation timestamp |

**Indexes**:
- `PRIMARY KEY(call_sid)`

---

## Migration Instructions

### Step 1: Run Migration SQL

```bash
# SSH into your server
ssh user@your-server.com

# Navigate to project directory
cd /path/to/Phone-agent

# Run migration
psql $DATABASE_URL -f migration_add_transcription_type.sql
```

**Expected Output**:
```
ALTER TABLE
UPDATE X
CREATE INDEX
COMMENT
```

### Step 2: Verify Migration

```sql
-- Check column exists
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'call_transcripts'
  AND column_name = 'transcription_type';

-- Should return:
-- column_name         | data_type      | column_default
-- transcription_type  | character varying | 'realtime'::character varying
```

### Step 3: Verify Index

```sql
-- Check index exists
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'call_transcripts'
  AND indexname = 'idx_transcripts_type';

-- Should return the index definition
```

---

## How Other Applications Should Query Transcripts

### Get Only Real-Time (AI Conversation) Transcripts

```sql
SELECT * FROM call_transcripts
WHERE call_sid = 'CA123...'
  AND transcription_type = 'realtime'
  AND is_final = TRUE
ORDER BY segment_number;
```

**Use Case**: Display the AI conversation portion of a call.

---

### Get Only Batch (Diarized) Transcripts

```sql
SELECT * FROM call_transcripts
WHERE call_sid = 'CA123...'
  AND transcription_type = 'batch'
ORDER BY segment_number;
```

**Use Case**: Display the human agent conversation with accurate speaker labels.

---

### Get Complete Call Transcript (Both Types)

```sql
SELECT
  id,
  call_sid,
  speaker,
  text,
  transcription_type,
  timestamp,
  segment_number
FROM call_transcripts
WHERE call_sid = 'CA123...'
  AND is_final = TRUE
ORDER BY segment_number;
```

**Use Case**: Show the entire call from start to finish.

---

### Get Formatted Transcript for Display

```sql
SELECT
  CASE
    WHEN speaker = 'caller' THEN 'Caller'
    WHEN speaker = 'agent' THEN 'Agent'
    WHEN speaker = 'ai' THEN 'AI Assistant'
  END as speaker_label,
  text,
  TO_CHAR(timestamp, 'HH24:MI:SS') as time,
  transcription_type
FROM call_transcripts
WHERE call_sid = 'CA123...'
  AND is_final = TRUE
ORDER BY segment_number;
```

**Example Output**:
```
speaker_label | text                                  | time     | transcription_type
--------------+---------------------------------------+----------+-------------------
Caller        | I want to order some detergent.       | 14:32:15 | realtime
AI Assistant  | Perfect! Connecting you to Sales now. | 14:32:18 | realtime
Agent         | Hi, how can I help you today?         | 14:32:25 | batch
Caller        | I'd like to order 2 units.            | 14:32:28 | batch
```

---

### Separate Real-Time and Batch in Application Logic

**Python Example (SQLAlchemy)**:

```python
from database import get_session, CallTranscript

session = get_session()

# Get AI conversation transcripts
ai_conversation = session.query(CallTranscript).filter_by(
    call_sid='CA123...',
    transcription_type='realtime',
    is_final=True
).order_by(CallTranscript.segment_number).all()

# Get human conversation transcripts (diarized)
human_conversation = session.query(CallTranscript).filter_by(
    call_sid='CA123...',
    transcription_type='batch'
).order_by(CallTranscript.segment_number).all()

# Format for display
transcript = {
    'ai_portion': [{'speaker': t.speaker, 'text': t.text} for t in ai_conversation],
    'human_portion': [{'speaker': t.speaker, 'text': t.text} for t in human_conversation]
}
```

---

### Count Transcripts by Type

```sql
SELECT
  transcription_type,
  COUNT(*) as count,
  COUNT(DISTINCT call_sid) as num_calls
FROM call_transcripts
WHERE is_final = TRUE
GROUP BY transcription_type;
```

**Example Output**:
```
transcription_type | count | num_calls
-------------------+-------+-----------
realtime           | 1250  | 423
batch              | 876   | 187
```

---

## API Response Format Recommendation

When building APIs that return transcripts, structure the response to clearly separate transcript types:

```json
{
  "call_sid": "CA123...",
  "caller_phone": "+18166741783",
  "ai_conversation": [
    {
      "speaker": "caller",
      "text": "I want to order some detergent.",
      "timestamp": "2025-11-07T14:32:15Z",
      "segment": 1
    },
    {
      "speaker": "ai",
      "text": "Perfect! Connecting you to Sales now.",
      "timestamp": "2025-11-07T14:32:18Z",
      "segment": 2
    }
  ],
  "human_conversation": [
    {
      "speaker": "agent",
      "text": "Hi, how can I help you today?",
      "timestamp": "2025-11-07T14:32:25Z",
      "segment": 3
    },
    {
      "speaker": "caller",
      "text": "I'd like to order 2 units.",
      "timestamp": "2025-11-07T14:32:28Z",
      "segment": 4
    }
  ],
  "metadata": {
    "total_segments": 4,
    "ai_segments": 2,
    "human_segments": 2,
    "call_duration_seconds": 145
  }
}
```

---

## Important Notes for Dependent Applications

### 1. Backward Compatibility

- **Existing transcripts**: All existing records will have `transcription_type = 'realtime'`
- **Default value**: New inserts without specifying `transcription_type` will default to `'realtime'`
- **No breaking changes**: Queries without filtering by `transcription_type` will continue to work

### 2. Data Quality Differences

- **`realtime` transcripts**:
  - ✅ Available immediately during call
  - ❌ Speaker labels may be incorrect (especially after transfer)
  - ❌ May be fragmented or have duplicates
  - Use for: Real-time monitoring, live dashboards

- **`batch` transcripts**:
  - ✅ Highly accurate speaker labels (Deepgram diarization)
  - ✅ Clean, well-formatted segments
  - ❌ Only available 10-15 seconds after call ends
  - Use for: Historical records, analytics, reporting

### 3. When to Use Which Type

**Use `realtime` when**:
- Monitoring active calls in real-time
- Building live transcription dashboards
- Triggering alerts based on keywords during calls

**Use `batch` when**:
- Generating call summaries or reports
- Training AI models on conversation data
- Quality assurance / call review
- Compliance or legal documentation

### 4. Migration Impact

**Zero downtime**: The migration adds a column with a default value, so:
- No service interruption required
- Existing queries continue to work
- New code can immediately use the column

**Data volume**: Minimal impact
- Adds ~20 bytes per transcript record
- Index adds negligible storage

---

## Testing Queries

### Verify Migration Success

```sql
-- Should return rows with both types
SELECT
  transcription_type,
  COUNT(*)
FROM call_transcripts
GROUP BY transcription_type;
```

### Test Filtering Performance

```sql
-- Should use index
EXPLAIN ANALYZE
SELECT * FROM call_transcripts
WHERE transcription_type = 'batch'
  AND call_sid = 'CA123...';

-- Look for "Index Scan using idx_transcripts_type"
```

---

## Rollback Plan (If Needed)

If you need to remove the changes:

```sql
-- Drop index
DROP INDEX IF EXISTS idx_transcripts_type;

-- Remove column
ALTER TABLE call_transcripts
DROP COLUMN IF EXISTS transcription_type;
```

**⚠️ Warning**: Rollback will delete all `transcription_type` data. Only do this if absolutely necessary.

---

## Contact & Support

For questions about this schema change:
- Review: `TRANSCRIPTION_FIX_SUMMARY.md` for implementation details
- Check: Application logs for `[Batch Transcription]` messages
- Monitor: Admin dashboard at `/admin/calls` for transcript quality

---

**Migration Version**: 1.0
**Last Updated**: 2025-11-07
**Compatibility**: PostgreSQL 12+
