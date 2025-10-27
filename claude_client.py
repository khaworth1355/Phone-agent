"""
Claude AI Client Module
Handles conversation with Claude AI
"""
import asyncio
from anthropic import Anthropic
from config import Config
from typing import List, Dict, Optional


class ClaudeAgent:
    """Manages conversation with Claude AI"""

    def __init__(self, system_prompt: Optional[str] = None, conversation_history: Optional[List[Dict]] = None):
        """
        Initialize Claude agent

        Args:
            system_prompt: System prompt to set context for Claude (uses config default if None)
            conversation_history: Existing conversation history to continue from
        """
        self.client = None
        self.conversation_history: List[Dict[str, str]] = conversation_history or []
        self.api_key = Config.ANTHROPIC_API_KEY
        self.model = Config.CLAUDE_MODEL

        # Use config system prompt or provided one
        self.system_prompt = system_prompt or Config.CLAUDE_SYSTEM_PROMPT

        print(f"[Claude] Agent initialized")
        print(f"[Claude] Model: {self.model}")
        print(f"[Claude] History: {len(self.conversation_history)} messages")

    def _ensure_client(self):
        """Lazy-load the Anthropic client"""
        if self.client is None:
            try:
                self.client = Anthropic(api_key=self.api_key)
                print(f"[Claude] Client connected")
            except Exception as e:
                print(f"[Claude] Error initializing client: {e}")
                raise

    def add_user_message(self, text: str) -> None:
        """
        Add user message to conversation history

        Args:
            text: User's message text
        """
        self.conversation_history.append({
            "role": "user",
            "content": text
        })
        print(f"[Claude] Added user message: '{text}'")

    async def get_response(self, user_text: Optional[str] = None, timeout: float = None) -> str:
        """
        Get Claude's response to user input (async with timeout)

        Args:
            user_text: Optional user text to add before getting response
                      If None, uses existing conversation history
            timeout: Timeout in seconds (uses Config.RESPONSE_TIMEOUT if None)

        Returns:
            Claude's response text
        """
        timeout = timeout or Config.RESPONSE_TIMEOUT

        try:
            # Ensure client is initialized
            self._ensure_client()

            # Add user message if provided
            if user_text:
                self.add_user_message(user_text)

            print(f"[Claude] Sending request with {len(self.conversation_history)} messages (timeout: {timeout}s)")

            # Call Claude API with timeout
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.messages.create,
                    model=self.model,
                    max_tokens=150,  # Further reduced for maximum speed
                    system=self.system_prompt,
                    messages=self.conversation_history
                ),
                timeout=timeout
            )

            # Extract response text
            assistant_message = response.content[0].text

            # Add to conversation history
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })

            print(f"[Claude] Response ({len(assistant_message)} chars): '{assistant_message}'")
            return assistant_message

        except asyncio.TimeoutError:
            print(f"[Claude] ⏱️ Timeout after {timeout}s")
            return "I'm sorry, I'm taking too long to respond. Could you repeat that?"

        except Exception as e:
            print(f"[Claude] ❌ Error getting response: {e}")
            import traceback
            traceback.print_exc()
            return "I'm sorry, I'm having trouble processing that right now."

    def clear_history(self) -> None:
        """Clear conversation history"""
        self.conversation_history = []
        print("[Claude] Conversation history cleared")

    def get_history_length(self) -> int:
        """Get number of messages in conversation history"""
        return len(self.conversation_history)