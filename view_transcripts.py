"""
View transcripts from database for a specific call
Usage: python view_transcripts.py <call_sid>
"""
import sys
from database import get_session, CallTranscript, CallRoute

def view_transcripts(call_sid):
    """View all transcripts for a call"""
    session = get_session()

    try:
        # Get routing info
        print("=" * 80)
        print(f"Call Transcripts for: {call_sid}")
        print("=" * 80)

        route = session.query(CallRoute).filter_by(call_sid=call_sid).first()
        if route:
            print(f"\nRouting Info:")
            print(f"  Department: {route.routing_decision}")
            print(f"  Method: {route.routing_method}")
            print(f"  Reason: {route.routing_reason}")
            print(f"  Confidence: {route.confidence_score}")
            print(f"  Routed At: {route.routed_at}")
            if route.agent_answered_at:
                print(f"  Agent Answered: {route.agent_answered_at}")
            if route.call_ended_at:
                print(f"  Call Ended: {route.call_ended_at}")
                print(f"  Duration: {route.call_duration_seconds}s")
        else:
            print("\nNo routing info found (call may not have been routed yet)")

        # Get transcripts
        transcripts = session.query(CallTranscript).filter_by(
            call_sid=call_sid,
            is_final=True
        ).order_by(CallTranscript.timestamp).all()

        if not transcripts:
            print(f"\n❌ No transcripts found for call {call_sid}")
            return

        print(f"\n{'=' * 80}")
        print(f"Transcript ({len(transcripts)} segments)")
        print(f"{'=' * 80}\n")

        for t in transcripts:
            timestamp = t.timestamp.strftime("%H:%M:%S")
            speaker_label = t.speaker.upper().ljust(7)
            print(f"[{timestamp}] {speaker_label}: {t.text}")

        print(f"\n{'=' * 80}")
        print(f"Total segments: {len(transcripts)}")
        print(f"{'=' * 80}\n")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


def list_recent_calls(limit=10):
    """List recent calls"""
    session = get_session()

    try:
        routes = session.query(CallRoute).order_by(
            CallRoute.created_at.desc()
        ).limit(limit).all()

        if not routes:
            print("No calls found in database")
            return

        print(f"\nRecent {limit} Calls:")
        print("=" * 80)
        for route in routes:
            created = route.created_at.strftime("%Y-%m-%d %H:%M:%S")
            print(f"{route.call_sid} - {route.routing_decision} - {created}")
        print("=" * 80)
        print(f"\nUsage: python view_transcripts.py <call_sid>")

    finally:
        session.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python view_transcripts.py <call_sid>")
        print("   or: python view_transcripts.py --list")
        print()
        list_recent_calls()
    elif sys.argv[1] == '--list':
        list_recent_calls(20)
    else:
        call_sid = sys.argv[1]
        view_transcripts(call_sid)
