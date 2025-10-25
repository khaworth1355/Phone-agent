"""
Call Manager - Manages active calls and transcripts
"""
import os
from datetime import datetime


class CallManager:
    """Manages call state and transcripts"""

    def __init__(self):
        self.calls = {}

    def create_call(self, call_sid, caller_number):
        """Create a new call"""
        self.calls[call_sid] = {
            'call_sid': call_sid,
            'caller_number': caller_number,
            'start_time': datetime.now(),
            'transcripts': []
        }
        print(f"\n[Call Manager] New call: {call_sid}")
        print(f"[Call Manager] From: {caller_number}\n")

    def add_transcript(self, call_sid, text, is_final, speaker='Caller'):
        """
        Add transcript to call

        Args:
            call_sid: Twilio call SID
            text: Transcript text
            is_final: Whether this is a final transcript
            speaker: Who is speaking ('Caller' or 'AI')
        """
        if call_sid not in self.calls:
            return

        self.calls[call_sid]['transcripts'].append({
            'text': text,
            'is_final': is_final,
            'speaker': speaker,
            'timestamp': datetime.now()
        })

        # Print to console
        if is_final:
            print(f"\n{'='*80}")
            print(f"[FINAL TRANSCRIPT - {speaker}]")
            print(f"{'='*80}")
            print(f"{text}")
            print(f"{'='*80}\n")
        else:
            print(f"[INTERIM - {speaker}] {text}")

    def end_call(self, call_sid):
        """End call and save transcript"""
        if call_sid not in self.calls:
            return

        call = self.calls[call_sid]
        call['end_time'] = datetime.now()

        # Save transcript to file
        self._save_transcript(call)

        # Clean up
        del self.calls[call_sid]
        print(f"[Call Manager] Call ended: {call_sid}\n")

    def _save_transcript(self, call):
        """Save transcript to file with timestamp filename (final transcripts only with speaker labels)"""
        try:
            # Create transcripts directory
            os.makedirs('transcripts', exist_ok=True)

            # Generate filename from timestamp
            timestamp = call['start_time'].strftime('%Y%m%d_%H%M%S')
            filename = f"transcripts/{timestamp}.txt"

            # Get final transcripts only
            final_transcripts = [t for t in call['transcripts'] if t['is_final']]

            # Calculate duration
            duration = (call['end_time'] - call['start_time']).total_seconds()

            # Write file
            with open(filename, 'w') as f:
                # Header
                f.write(f"Call SID: {call['call_sid']}\n")
                f.write(f"Caller: {call['caller_number']}\n")
                f.write(f"Start: {call['start_time'].strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"End: {call['end_time'].strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Duration: {duration:.1f} seconds\n")
                f.write(f"\n{'='*60}\n")
                f.write(f"TRANSCRIPT (Final only)\n")
                f.write(f"{'='*60}\n\n")

                # Write final transcripts with speaker labels and timestamps
                if final_transcripts:
                    for t in final_transcripts:
                        time_str = t['timestamp'].strftime('%H:%M:%S')
                        speaker = t.get('speaker', 'Unknown')
                        f.write(f"[{time_str}] {speaker}: {t['text']}\n")
                else:
                    f.write("(No speech detected)\n")

            print(f"[Call Manager] Transcript saved: {filename}")

        except Exception as e:
            print(f"[Call Manager] Error saving transcript: {e}")


# Global instance
call_manager = CallManager()
