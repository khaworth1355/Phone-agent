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
    COLLECTING_CUSTOMER_INFO = "collecting_customer_info"


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

        # Predictive response tracking
        self.interim_history = []  # Track last N interim transcripts
        self.predictive_response_triggered = False
        self.predictive_response_task = None  # Store task for cancellation

        # Conversation history for Claude
        self.conversation_history = []

        # Detergent order tracking
        self.collecting_detergent_info = False
        self.detergent_customer_name = None
        self.detergent_customer_phone = None

        # Callbacks
        self.on_user_finished = None  # Callback when user finishes speaking
        self.on_barge_in = None  # Callback when user interrupts AI
        self.on_predictive_trigger = None  # Callback for predictive response

        # Settings
        self.pause_threshold = Config.PAUSE_THRESHOLD
        self.predictive_enabled = Config.PREDICTIVE_RESPONSES
        self.interim_stability_threshold = Config.INTERIM_STABILITY_THRESHOLD

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

            # Track interim transcripts for predictive response
            if self.predictive_enabled and not self.predictive_response_triggered:
                self._check_predictive_trigger(text)

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

    def _check_predictive_trigger(self, interim_text: str):
        """
        Check if interim transcript is stable enough to trigger predictive response

        Args:
            interim_text: Current interim transcript
        """
        if not interim_text or len(interim_text.strip()) < 10:
            # Too short to be meaningful
            return

        # Add to history
        self.interim_history.append(interim_text)

        # Keep only last N transcripts
        if len(self.interim_history) > self.interim_stability_threshold + 2:
            self.interim_history.pop(0)

        # Check if we have enough history
        if len(self.interim_history) < self.interim_stability_threshold:
            return

        # Check if last N transcripts are similar (stable)
        recent = self.interim_history[-self.interim_stability_threshold:]

        # Count how many are substantially similar
        matches = 0
        base = recent[0].lower()
        for transcript in recent[1:]:
            # Check if transcripts are very similar (>80% overlap)
            if self._similarity_ratio(base, transcript.lower()) > 0.8:
                matches += 1

        # If stable, trigger predictive response
        if matches >= self.interim_stability_threshold - 1:
            print(f"\n[Predictive] 🚀 Stable interim detected: '{interim_text}'")
            print(f"[Predictive] Starting early response generation...")
            self.predictive_response_triggered = True
            self.interim_history = []  # Clear history

            # Trigger callback
            if self.on_predictive_trigger:
                self.on_predictive_trigger(interim_text)

    def _similarity_ratio(self, str1: str, str2: str) -> float:
        """Calculate similarity ratio between two strings"""
        # Simple word-based similarity
        words1 = set(str1.split())
        words2 = set(str2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def cancel_predictive_response(self):
        """Cancel any in-flight predictive response"""
        if self.predictive_response_task and not self.predictive_response_task.done():
            self.predictive_response_task.cancel()
            print(f"[Predictive] ❌ Cancelled in-flight response")

        self.predictive_response_triggered = False
        self.predictive_response_task = None
        self.interim_history = []

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

    def start_collecting_detergent_info(self):
        """Mark that we're starting to collect detergent customer info"""
        self.collecting_detergent_info = True
        self.detergent_customer_name = None
        self.detergent_customer_phone = None
        print(f"[ConversationManager] Started collecting detergent order info")

    def set_detergent_customer_name(self, name: str):
        """Store customer name for detergent order"""
        self.detergent_customer_name = name
        print(f"[ConversationManager] Customer name: {name}")

    def set_detergent_customer_phone(self, phone: str):
        """Store customer phone for detergent order"""
        self.detergent_customer_phone = phone
        print(f"[ConversationManager] Customer phone: {phone}")

    def has_complete_detergent_info(self) -> bool:
        """Check if we have all required detergent order info"""
        return (self.collecting_detergent_info and
                self.detergent_customer_name is not None and
                self.detergent_customer_phone is not None)

    def get_detergent_order_info(self) -> dict:
        """Get collected detergent order information"""
        return {
            'name': self.detergent_customer_name,
            'phone': self.detergent_customer_phone,
            'call_sid': self.call_sid
        }

    def clear_detergent_info(self):
        """Clear detergent order info"""
        self.collecting_detergent_info = False
        self.detergent_customer_name = None
        self.detergent_customer_phone = None
        print(f"[ConversationManager] Cleared detergent order info")
