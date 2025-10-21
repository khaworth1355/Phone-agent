"""
Call Manager Module
Manages active call states and transcripts
"""
import os
from datetime import datetime
from typing import Dict, Optional


class CallManager:
    """Manages active calls and their data"""

    def __init__(self):
        """Initialize the call manager with empty calls dictionary"""
        self.active_calls: Dict[str, dict] = {}

    def create_call(self, call_sid: str, caller_number: str) -> dict:
        """
        Create a new call record

        Args:
            call_sid: Twilio's unique call identifier
            caller_number: The caller's phone number

        Returns:
            The created call record
        """
        call_data = {
            'call_sid': call_sid,
            'caller_number': caller_number,
            'start_time': datetime.now(),
            'transcript': [],
            'status': 'active',
            'stream_sid': None
        }

        self.active_calls[call_sid] = call_data

        print(f"\n[Call Manager] Created call record for {call_sid}")
        print(f"[Call Manager] Caller: {caller_number}")
        print(f"[Call Manager] Active calls: {len(self.active_calls)}\n")

        return call_data

    def get_call(self, call_sid: str) -> Optional[dict]:
        """
        Get call data by call_sid

        Args:
            call_sid: The call identifier

        Returns:
            Call data if found, None otherwise
        """
        return self.active_calls.get(call_sid)

    def add_transcript(self, call_sid: str, text: str, is_final: bool = False) -> None:
        """
        Add transcribed text to a call's transcript

        Args:
            call_sid: The call identifier
            text: The transcribed text
            is_final: Whether this is a final transcript or interim
        """
        call = self.get_call(call_sid)
        if not call:
            print(f"[Call Manager] Warning: Call {call_sid} not found")
            return

        transcript_entry = {
            'text': text,
            'timestamp': datetime.now(),
            'is_final': is_final
        }

        call['transcript'].append(transcript_entry)

        # Print transcript with appropriate formatting
        prefix = "[FINAL]" if is_final else "[INTERIM]"
        print(f"{prefix} {text}")

    def set_stream_sid(self, call_sid: str, stream_sid: str) -> None:
        """
        Set the stream SID for a call

        Args:
            call_sid: The call identifier
            stream_sid: Twilio's media stream identifier
        """
        call = self.get_call(call_sid)
        if call:
            call['stream_sid'] = stream_sid
            print(f"[Call Manager] Set stream SID for call {call_sid}: {stream_sid}")

    def end_call(self, call_sid: str) -> Optional[dict]:
        """
        Mark a call as ended, save transcript to file, and return its data

        Args:
            call_sid: The call identifier

        Returns:
            The final call data if found
        """
        call = self.active_calls.get(call_sid)
        if not call:
            return None

        call['status'] = 'completed'
        call['end_time'] = datetime.now()

        # Calculate duration
        duration = (call['end_time'] - call['start_time']).total_seconds()
        call['duration_seconds'] = duration

        print(f"\n[Call Manager] Call {call_sid} ended")
        print(f"[Call Manager] Duration: {duration:.2f} seconds")
        print(f"[Call Manager] Transcript entries: {len(call['transcript'])}")

        # NEW: Save transcript to file
        try:
            filename = f"transcripts/{call_sid}.txt"
            with open(filename, 'w') as f:
                f.write(f"Call SID: {call_sid}\n")
                f.write(f"Caller: {call['caller_number']}\n")
                f.write(f"Start Time: {call['start_time'].strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"End Time: {call['end_time'].strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Duration: {duration:.2f} seconds\n")
                f.write(f"Transcript Entries: {len(call['transcript'])}\n")
                f.write(f"\n{'=' * 60}\n")
                f.write(f"FULL TRANSCRIPT\n")
                f.write(f"{'=' * 60}\n\n")

                # Write final transcripts only
                final_transcript = self.get_full_transcript(call_sid, final_only=True)
                f.write(final_transcript)

                f.write(f"\n\n{'=' * 60}\n")
                f.write(f"DETAILED TRANSCRIPT (with timestamps)\n")
                f.write(f"{'=' * 60}\n\n")

                # Write all transcript entries with timestamps
                for entry in call['transcript']:
                    timestamp = entry['timestamp'].strftime('%H:%M:%S')
                    elapsed = entry.get('elapsed_seconds', 0)
                    final_marker = "[FINAL]" if entry['is_final'] else "[INTERIM]"
                    f.write(f"[{timestamp}] [{elapsed:.1f}s] {final_marker} {entry['text']}\n")

            print(f"[Call Manager] Transcript saved to {filename}")

        except Exception as e:
            print(f"[Call Manager] Error saving transcript: {e}")

        # Remove from active calls
        del self.active_calls[call_sid]

        return call

    def get_full_transcript(self, call_sid: str, final_only: bool = True) -> str:
        """
        Get the full transcript for a call

        Args:
            call_sid: The call identifier
            final_only: If True, only return final transcripts

        Returns:
            Concatenated transcript text
        """
        call = self.get_call(call_sid)
        if not call:
            return ""

        if final_only:
            texts = [entry['text'] for entry in call['transcript'] if entry['is_final']]
        else:
            texts = [entry['text'] for entry in call['transcript']]

        return " ".join(texts)


# Create a global instance
call_manager = CallManager()
