# Transcription Fix - Deployment Instructions

**Date**: 2025-11-07
**Target Environment**: PostgreSQL on Remote Server

---

## Quick Start

### 1. Review Documentation

Read these files to understand the changes:
- ✅ `DATABASE_SCHEMA_CHANGES.md` - **Complete schema documentation for dependent apps**
- ✅ `TRANSCRIPTION_FIX_SUMMARY.md` - Implementation details and architecture
- ✅ `migration_add_transcription_type.sql` - SQL migration script

### 2. Deploy Code Changes

```bash
# SSH into your server
ssh user@your-server.com

# Navigate to project directory
cd /path/to/Phone-agent

# Pull latest code
git pull origin database  # or your branch name

# Restart application
pm2 restart phone-agent
```

### 3. Run Database Migration

```bash
# Still on your server, in the project directory

# Run the migration
psql $DATABASE_URL -f migration_add_transcription_type.sql
```

**Expected Output**:
```
ALTER TABLE
UPDATE 0
CREATE INDEX
COMMENT
```

### 4. Verify Migration

```bash
# Check the column was added
psql $DATABASE_URL -c "SELECT column_name, data_type, column_default FROM information_schema.columns WHERE table_name = 'call_transcripts' AND column_name = 'transcription_type';"
```

**Expected Output**:
```
    column_name     |     data_type     |        column_default
--------------------+-------------------+-------------------------------
 transcription_type | character varying | 'realtime'::character varying
(1 row)
```

### 5. Test the System

Make a test call:
1. Call your Twilio number
2. Say "I'd like to talk to sales"
3. Wait for transfer
4. Have a brief conversation with the "agent" (yourself on another phone)
5. End the call
6. Wait 15 seconds
7. Check logs for `[Batch Transcription]` messages

```bash
# View recent logs
pm2 logs phone-agent --lines 100
```

Look for:
```
[Batch Transcription] Processing recording for call CA123...
[Batch Transcription] Found recording: RE456...
[Batch Transcription] Downloading from Twilio...
[Batch Transcription] Sending to Deepgram with diarization...
[Batch Transcription] ✓ Deepgram transcription complete
[Batch Transcription] caller: Hi, I'd like to order detergent.
[Batch Transcription] agent: Great! How many units?
[Batch Transcription] ✅ Stored 8 diarized transcript segments
```

### 6. Verify in Database

```bash
# Check transcripts exist with both types
psql $DATABASE_URL -c "SELECT transcription_type, COUNT(*) FROM call_transcripts GROUP BY transcription_type;"
```

**Expected Output**:
```
 transcription_type | count
--------------------+-------
 realtime           |    15
 batch              |     8
(2 rows)
```

---

## Files Changed (Git Status)

Modified files:
- `app.py` - Main application (transcription logic)
- `conversation_manager.py` - Agent join handling
- `conference_manager.py` - Recording metadata
- `database.py` - Schema update

New files:
- `migration_add_transcription_type.sql` - Migration script
- `DATABASE_SCHEMA_CHANGES.md` - Schema documentation
- `TRANSCRIPTION_FIX_SUMMARY.md` - Implementation summary
- `DEPLOYMENT_INSTRUCTIONS.md` - This file

---

## For Dependent Applications

If you have other applications reading from this database:

### Update Your Applications to Use New Column

**Before** (old code):
```python
# Get all transcripts
transcripts = session.query(CallTranscript).filter_by(
    call_sid=call_sid,
    is_final=True
).all()
```

**After** (recommended):
```python
# Get AI conversation
ai_transcripts = session.query(CallTranscript).filter_by(
    call_sid=call_sid,
    transcription_type='realtime',
    is_final=True
).all()

# Get human conversation (accurate speakers)
human_transcripts = session.query(CallTranscript).filter_by(
    call_sid=call_sid,
    transcription_type='batch'
).all()
```

### API Changes (If You Have External APIs)

Update your API responses to include `transcription_type`:

```json
{
  "call_sid": "CA123...",
  "transcripts": [
    {
      "speaker": "caller",
      "text": "I want to order detergent",
      "type": "realtime",
      "timestamp": "2025-11-07T14:32:15Z"
    },
    {
      "speaker": "ai",
      "text": "Connecting you to sales",
      "type": "realtime",
      "timestamp": "2025-11-07T14:32:18Z"
    },
    {
      "speaker": "agent",
      "text": "Hi, how can I help?",
      "type": "batch",
      "timestamp": "2025-11-07T14:32:25Z"
    }
  ]
}
```

---

## Rollback Plan

If something goes wrong and you need to rollback:

### Rollback Code

```bash
# On your server
cd /path/to/Phone-agent
git checkout <previous-commit-hash>
pm2 restart phone-agent
```

### Rollback Database (⚠️ Destroys Data)

```bash
# Only if absolutely necessary
psql $DATABASE_URL -c "DROP INDEX IF EXISTS idx_transcripts_type;"
psql $DATABASE_URL -c "ALTER TABLE call_transcripts DROP COLUMN IF EXISTS transcription_type;"
```

**Note**: This will remove the `transcription_type` column and lose that data. Only do this if you're reverting the entire feature.

---

## Monitoring

### Check System Health

```bash
# Application status
pm2 status

# Recent logs
pm2 logs phone-agent --lines 50

# Follow logs in real-time
pm2 logs phone-agent --lines 0 --raw
```

### Check Database Connection

```bash
psql $DATABASE_URL -c "SELECT version();"
```

### Monitor Transcription Processing

```bash
# Filter for batch transcription logs
pm2 logs phone-agent | grep "Batch Transcription"
```

---

## Common Issues

### Issue: Migration already applied

**Symptom**: Error about column already exists

**Solution**: The migration uses `IF NOT EXISTS`, so it's safe to run multiple times. Ignore this error.

### Issue: No batch transcripts appearing

**Symptom**: Only seeing `realtime` transcripts in database

**Possible Causes**:
1. No calls have been transferred to agents yet (batch only happens after transfer)
2. Recording not enabled properly (check Twilio console)
3. Deepgram API error (check logs for errors)

**Debug Steps**:
```bash
# Check if recording is happening
psql $DATABASE_URL -c "SELECT * FROM call_routes ORDER BY routed_at DESC LIMIT 5;"

# Check logs for errors
pm2 logs phone-agent --lines 200 | grep -i "error\|failed"
```

### Issue: Transcription quality still poor

**Symptom**: Speaker labels still incorrect in batch transcripts

**Solution**: This is rare but can happen if speakers have similar voices. Deepgram's diarization is ~95% accurate. If you need 100% accuracy, you may need to train a custom speaker model.

---

## Support & Documentation

- Complete schema: `DATABASE_SCHEMA_CHANGES.md`
- Implementation details: `TRANSCRIPTION_FIX_SUMMARY.md`
- Twilio recordings: https://www.twilio.com/docs/voice/api/recording
- Deepgram diarization: https://developers.deepgram.com/docs/diarization

---

**Deployment Checklist**:
- [ ] Review `DATABASE_SCHEMA_CHANGES.md`
- [ ] Pull latest code
- [ ] Run migration SQL
- [ ] Restart application
- [ ] Make test call
- [ ] Verify batch transcripts appear
- [ ] Update dependent applications (if any)
- [ ] Monitor logs for 24 hours

**Estimated Deployment Time**: 10-15 minutes
**Expected Downtime**: 0 seconds (rolling update)
