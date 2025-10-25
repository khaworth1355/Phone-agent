"""
Conversation Manager - Handles conversation flow and state
"""
import time
from datetime import datetime
from enum import Enum
from typing import Optional, Callable
from config import Config


class ConversationState(Enum):
    """Conversation states"""
    IDLE = "idle"
    USER_SPEAKING = "user_speaking"
    WAITING_FOR_PAUSE = "waiting_for_pause"
    AI_THINKING = "ai_thinking"
    AI_SPEAKING = "ai_speaking"


class ConversationManager:
    """Manages conversation flow, pause detection, and state"""

    def __init__(self, call_sid: str):
        """
        Initialize conversation manager

        Args:
            call_sid: Twilio call SID
        """
        self.call_sid = call_sid
        self.state = ConversationState.IDLE

        # Speech buffering
        self.current_user_text = ""
        self.interim_buffer = ""
        self.last_speech_time = None
        self.last_final_time = None

        # Conversation history for Claude
        self.conversation_history = []

        # Callbacks
        self.on_user_finished = None  # Callback when user finishes speaking
        self.on_barge_in = None  # Callback when user interrupts AI

        # Settings
        self.pause_threshold = Config.PAUSE_THRESHOLD

        print(f"[ConversationManager] Initialized for call {call_sid}")
        print(f"[ConversationManager] Pause threshold: {self.pause_threshold}s")

    def add_transcript(self, text: str, is_final: bool):
        """
        Add transcript from Deepgram

        Args:
            text: Transcript text
            is_final: Whether this is a final transcript
        """
        if not text:
            return

        current_time = time.time()

        # Update last speech time
        self.last_speech_time = current_time

        # Handle barge-in
        if self.state == ConversationState.AI_SPEAKING:
            print(f"\n[ConversationManager] 🔴 BARGE-IN DETECTED!")
            print(f"[ConversationManager] User interrupted AI: '{text}'\n")
            self._trigger_barge_in()
            self.state = ConversationState.USER_SPEAKING
            self.current_user_text = ""  # Reset buffer

        # Update state if needed
        if self.state == ConversationState.IDLE:
            self.state = ConversationState.USER_SPEAKING
            print(f"\n[ConversationManager] User started speaking")

        if is_final:
            # Final transcript
            self.last_final_time = current_time
            self.current_user_text += " " + text if self.current_user_text else text
            self.interim_buffer = ""

            print(f"[ConversationManager] Final: '{text}'")
            print(f"[ConversationManager] Accumulated: '{self.current_user_text}'")

            # Start waiting for pause
            if self.state == ConversationState.USER_SPEAKING:
                self.state = ConversationState.WAITING_FOR_PAUSE
                print(f"[ConversationManager] Waiting for {self.pause_threshold}s pause...")
        else:
            # Interim transcript
            self.interim_buffer = text

    def check_for_pause(self) -> bool:
        """
        Check if user has paused speaking

        Returns:
            True if pause detected and we should trigger AI response
        """
        if self.state != ConversationState.WAITING_FOR_PAUSE:
            return False

        if not self.last_final_time:
            return False

        # Calculate time since last final transcript
        time_since_last_speech = time.time() - self.last_final_time

        if time_since_last_speech >= self.pause_threshold:
            print(f"\n[ConversationManager] ✅ PAUSE DETECTED ({time_since_last_speech:.1f}s)")
            print(f"[ConversationManager] User said: '{self.current_user_text}'\n")

            # Trigger AI response
            self.state = ConversationState.AI_THINKING
            self._trigger_user_finished()
            return True

        return False

    def start_ai_response(self):
        """Mark that AI has started speaking"""
        self.state = ConversationState.AI_SPEAKING
        print(f"[ConversationManager] AI started speaking")

    def finish_ai_response(self, ai_text: str):
        """
        Mark that AI has finished speaking

        Args:
            ai_text: What the AI said
        """
        # Add to conversation history
        self.conversation_history.append({
            'role': 'user',
            'content': self.current_user_text
        })
        self.conversation_history.append({
            'role': 'assistant',
            'content': ai_text
        })

        # Reset state
        self.current_user_text = ""
        self.interim_buffer = ""
        self.state = ConversationState.IDLE

        print(f"[ConversationManager] AI finished speaking")
        print(f"[ConversationManager] Conversation history has {len(self.conversation_history)} messages\n")

    def get_user_text(self) -> str:
        """Get the current accumulated user text"""
        return self.current_user_text

    def get_conversation_history(self) -> list:
        """Get the full conversation history for Claude"""
        return self.conversation_history.copy()

    def _trigger_user_finished(self):
        """Internal: Trigger user finished callback"""
        if self.on_user_finished:
            self.on_user_finished(self.current_user_text)

    def _trigger_barge_in(self):
        """Internal: Trigger barge-in callback"""
        if self.on_barge_in:
            self.on_barge_in()

    def reset(self):
        """Reset conversation state (for new call)"""
        self.state = ConversationState.IDLE
        self.current_user_text = ""
        self.interim_buffer = ""
        self.last_speech_time = None
        self.last_final_time = None
        print(f"[ConversationManager] Reset")
