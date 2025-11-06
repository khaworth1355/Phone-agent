"""
Conference Manager - Track active conferences and participants
Enables continuous transcription during call routing by maintaining Media Stream
"""
from datetime import datetime
from typing import Optional, Dict, List


class ConferenceManager:
    """Manages Twilio conference rooms and participant tracking"""

    def __init__(self):
        self.active_conferences: Dict[str, dict] = {}  # conference_name -> metadata
        print("[ConferenceManager] Initialized")

    def create_conference(self, call_sid: str, caller_phone: str) -> str:
        """
        Register new conference room for incoming call

        Args:
            call_sid: Twilio call SID
            caller_phone: Caller's phone number

        Returns:
            Conference name (call-room-{call_sid})
        """
        conference_name = f"call-room-{call_sid}"

        self.active_conferences[conference_name] = {
            'call_sid': call_sid,
            'caller_phone': caller_phone,
            'created_at': datetime.utcnow(),
            'participants': [],
            'agent_joined': False,
            'caller_participant_sid': None,
            'agent_participant_sid': None
        }

        print(f"[ConferenceManager] Created conference: {conference_name}")
        return conference_name

    def add_participant(self, conference_name: str, participant_sid: str, role: str):
        """
        Track when participant joins conference

        Args:
            conference_name: Name of conference room
            participant_sid: Twilio participant SID
            role: 'caller' or 'agent'
        """
        if conference_name not in self.active_conferences:
            print(f"[ConferenceManager] Warning: Conference {conference_name} not found")
            return

        participant_info = {
            'sid': participant_sid,
            'role': role,
            'joined_at': datetime.utcnow()
        }

        self.active_conferences[conference_name]['participants'].append(participant_info)

        if role == 'agent':
            self.active_conferences[conference_name]['agent_joined'] = True
            self.active_conferences[conference_name]['agent_participant_sid'] = participant_sid
            print(f"[ConferenceManager] Agent joined conference: {conference_name}")
        elif role == 'caller':
            self.active_conferences[conference_name]['caller_participant_sid'] = participant_sid
            print(f"[ConferenceManager] Caller joined conference: {conference_name}")

    def get_conference_info(self, call_sid: str) -> Optional[dict]:
        """
        Get conference metadata by call_sid

        Args:
            call_sid: Twilio call SID

        Returns:
            Conference metadata dict or None if not found
        """
        conference_name = f"call-room-{call_sid}"
        return self.active_conferences.get(conference_name)

    def get_conference_by_name(self, conference_name: str) -> Optional[dict]:
        """
        Get conference metadata by conference name

        Args:
            conference_name: Conference room name

        Returns:
            Conference metadata dict or None if not found
        """
        return self.active_conferences.get(conference_name)

    def is_agent_in_conference(self, call_sid: str) -> bool:
        """
        Check if agent has joined the conference

        Args:
            call_sid: Twilio call SID

        Returns:
            True if agent has joined, False otherwise
        """
        info = self.get_conference_info(call_sid)
        return info['agent_joined'] if info else False

    def get_participant_count(self, conference_name: str) -> int:
        """
        Get number of participants in conference

        Args:
            conference_name: Conference room name

        Returns:
            Number of participants
        """
        info = self.get_conference_by_name(conference_name)
        return len(info['participants']) if info else 0

    def cleanup_conference(self, conference_name: str):
        """
        Remove conference after call ends

        Args:
            conference_name: Conference room name
        """
        if conference_name in self.active_conferences:
            conf_info = self.active_conferences[conference_name]
            duration = (datetime.utcnow() - conf_info['created_at']).total_seconds()
            print(f"[ConferenceManager] Cleaning up conference: {conference_name} (duration: {duration:.1f}s)")
            del self.active_conferences[conference_name]
        else:
            print(f"[ConferenceManager] Conference {conference_name} not found for cleanup")

    def list_active_conferences(self) -> List[str]:
        """
        Get list of all active conference names

        Returns:
            List of conference names
        """
        return list(self.active_conferences.keys())

    def get_stats(self) -> dict:
        """
        Get statistics about active conferences

        Returns:
            Dict with conference statistics
        """
        total = len(self.active_conferences)
        with_agents = sum(1 for conf in self.active_conferences.values() if conf['agent_joined'])

        return {
            'total_conferences': total,
            'conferences_with_agents': with_agents,
            'conferences_waiting': total - with_agents
        }


# Global instance
conference_manager = ConferenceManager()
