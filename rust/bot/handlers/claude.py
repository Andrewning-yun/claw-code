"""Claude conversation handler.

Handles /claude commands for interacting with Claude API.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..claude_client import ClaudeClient, ClaudeResponse
from ..scheduler import TaskScheduler

logger = logging.getLogger(__name__)


@dataclass
class ConversationSession:
    """Represents a conversation session with Claude."""
    id: str
    created_at: datetime = field(default_factory=datetime.now)
    messages: list[dict[str, str]] = field(default_factory=list)
    message_count: int = 0
    
    def add_message(self, role: str, content: str) -> None:
        """Add a message to the session."""
        self.messages.append({"role": role, "content": content})
        self.message_count += 1


class ClaudeHandler:
    """Handler for Claude API conversations."""
    
    def __init__(self, client: ClaudeClient, scheduler: Optional[TaskScheduler] = None):
        """Initialize the Claude handler.
        
        Args:
            client: The Claude API client.
            scheduler: Optional task scheduler for scheduled conversations.
        """
        self.client = client
        self.scheduler = scheduler
        self.sessions: dict[str, ConversationSession] = {}
        self._current_session: Optional[ConversationSession] = None
        
    def create_session(self, session_id: Optional[str] = None) -> ConversationSession:
        """Create a new conversation session.
        
        Args:
            session_id: Optional session ID. Generated if not provided.
            
        Returns:
            The new conversation session.
        """
        if session_id is None:
            session_id = f"session_{len(self.sessions) + 1}"
            
        session = ConversationSession(id=session_id)
        self.sessions[session_id] = session
        
        if self._current_session is None:
            self._current_session = session
            
        logger.info(f"Created conversation session: {session_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID.
        
        Args:
            session_id: The session ID.
            
        Returns:
            The session or None if not found.
        """
        return self.sessions.get(session_id)
    
    def set_current_session(self, session_id: str) -> bool:
        """Set the current active session.
        
        Args:
            session_id: The session ID to make current.
            
        Returns:
            True if successful, False if session not found.
        """
        if session_id in self.sessions:
            self._current_session = self.sessions[session_id]
            return True
        return False
    
    def list_sessions(self) -> list[ConversationSession]:
        """List all sessions.
        
        Returns:
            List of all conversation sessions.
        """
        return list(self.sessions.values())
    
    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        system: Optional[str] = None,
    ) -> ClaudeResponse:
        """Send a chat message to Claude.
        
        Args:
            message: The user's message.
            session_id: Optional session ID to use.
            system: Optional system prompt.
            
        Returns:
            Claude's response.
        """
        # Get or create session
        if session_id and session_id in self.sessions:
            session = self.sessions[session_id]
        elif self._current_session:
            session = self._current_session
        else:
            session = self.create_session()
        
        # Add user message to history
        session.add_message("user", message)
        
        # Convert to API format
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in session.messages
        ]
        
        # Send to API
        response = await self.client.send_message(messages, system=system, stream=False)
        
        # Extract content
        content = ""
        for block in response.content:
            if hasattr(block, 'text'):
                content += block.text
        
        # Add assistant response to history
        session.add_message("assistant", content)
        
        return ClaudeResponse(
            content=content,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            stop_reason=response.stop_reason,
        )
    
    async def stream_chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        system: Optional[str] = None,
    ):
        """Stream a chat response from Claude.
        
        Args:
            message: The user's message.
            session_id: Optional session ID to use.
            system: Optional system prompt.
            
        Yields:
            Text deltas from the streaming response.
        """
        # Get or create session
        if session_id and session_id in self.sessions:
            session = self.sessions[session_id]
        elif self._current_session:
            session = self._current_session
        else:
            session = self.create_session()
        
        # Add user message to history
        session.add_message("user", message)
        
        # Convert to API format
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in session.messages
        ]
        
        # Stream from API
        full_content = ""
        async for text in self.client.stream_chat(message, system=system):
            full_content += text
            yield text
        
        # Add assistant response to history
        session.add_message("assistant", full_content)
    
    def clear_session(self, session_id: Optional[str] = None) -> bool:
        """Clear a session's history.
        
        Args:
            session_id: Session to clear. Clears current if not provided.
            
        Returns:
            True if cleared, False if session not found.
        """
        target = session_id or (self._current_session.id if self._current_session else None)
        
        if target and target in self.sessions:
            self.sessions[target].messages.clear()
            self.sessions[target].message_count = 0
            logger.info(f"Cleared session: {target}")
            return True
        return False
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session entirely.
        
        Args:
            session_id: ID of session to delete.
            
        Returns:
            True if deleted, False if not found.
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            
            if self._current_session and self._current_session.id == session_id:
                self._current_session = next(iter(self.sessions.values())) if self.sessions else None
                
            logger.info(f"Deleted session: {session_id}")
            return True
        return False
    
    def get_session_summary(self, session_id: str) -> Optional[dict[str, Any]]:
        """Get a summary of a session.
        
        Args:
            session_id: The session ID.
            
        Returns:
            Session summary or None if not found.
        """
        session = self.sessions.get(session_id)
        if not session:
            return None
            
        return {
            "id": session.id,
            "created_at": session.created_at.isoformat(),
            "message_count": session.message_count,
            "messages": [
                {"role": m["role"], "content": m["content"][:100] + "..." if len(m["content"]) > 100 else m["content"]}
                for m in session.messages[-5:]  # Last 5 messages
            ],
        }


def format_chat_response(response: ClaudeResponse) -> str:
    """Format a Claude response for display.
    
    Args:
        response: The Claude response.
        
    Returns:
        Formatted response string.
    """
    lines = [
        response.content,
        "",
        f"Model: {response.model}",
        f"Input tokens: {response.usage['input_tokens']}",
        f"Output tokens: {response.usage['output_tokens']}",
    ]
    
    if response.stop_reason:
        lines.append(f"Stop reason: {response.stop_reason}")
        
    return "\n".join(lines)