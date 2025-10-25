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

    def add_transcript(self, call_sid, text, is_final):
        """Add transcript to call"""
        if call_sid not in self.calls:
            return

        self.calls[call_sid]['transcripts'].append({
            'text': text,
            'is_final': is_final,
            'timestamp': datetime.now()
        })

        # Print to console
        if is_final:
            print(f"\n{'='*80}")
            print(f"[FINAL TRANSCRIPT]")
            print(f"{'='*80}")
            print(f"{text}")
            print(f"{'='*80}\n")
        else:
            print(f"[INTERIM] {text}")

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
        """Save transcript to file with timestamp filename"""
        try:
            # Create transcripts directory
            os.makedirs('transcripts', exist_ok=True)

            # Generate filename from timestamp
            timestamp = call['start_time'].strftime('%Y%m%d_%H%M%S')
            filename = f"transcripts/{timestamp}.txt"

            # Get final transcripts only
            final_texts = [t['text'] for t in call['transcripts'] if t['is_final']]
            full_transcript = ' '.join(final_texts)

            # Calculate duration
            duration = (call['end_time'] - call['start_time']).total_seconds()

            # Write file
            with open(filename, 'w') as f:
                f.write(f"Call SID: {call['call_sid']}\n")
                f.write(f"Caller: {call['caller_number']}\n")
                f.write(f"Start: {call['start_time'].strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"End: {call['end_time'].strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Duration: {duration:.1f} seconds\n")
                f.write(f"\n{'='*60}\n")
                f.write(f"TRANSCRIPT\n")
                f.write(f"{'='*60}\n\n")
                f.write(full_transcript if full_transcript else "(No speech detected)")
                f.write(f"\n\n{'='*60}\n")
                f.write(f"DETAILED LOG\n")
                f.write(f"{'='*60}\n\n")

                for t in call['transcripts']:
                    marker = "[FINAL]" if t['is_final'] else "[INTERIM]"
                    time_str = t['timestamp'].strftime('%H:%M:%S')
                    f.write(f"[{time_str}] {marker} {t['text']}\n")

            print(f"[Call Manager] Transcript saved: {filename}")

        except Exception as e:
            print(f"[Call Manager] Error saving transcript: {e}")


# Global instance
call_manager = CallManager()
