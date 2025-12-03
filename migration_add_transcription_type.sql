-- Migration: Add transcription_type column to call_transcripts table
-- Database: PostgreSQL
-- Date: 2025-11-07
-- Purpose: Distinguish between real-time (AI conversation) and batch (diarized post-call) transcripts

-- Add new column with default value 'realtime'
ALTER TABLE call_transcripts
ADD COLUMN IF NOT EXISTS transcription_type VARCHAR(20) DEFAULT 'realtime';

-- Update existing records to be 'realtime' (they are all from AI conversations)
UPDATE call_transcripts
SET transcription_type = 'realtime'
WHERE transcription_type IS NULL;

-- Create index for faster filtering by transcription type
CREATE INDEX IF NOT EXISTS idx_transcripts_type ON call_transcripts(transcription_type);

-- Add comment to explain the column
COMMENT ON COLUMN call_transcripts.transcription_type IS 'Type of transcription: realtime (during AI conversation) or batch (diarized post-call recording)';
