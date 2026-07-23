"""
app/voice/session_manager.py — Per-session state management.

Each WebSocket connection gets a VoiceSession that tracks:
  - Unique session ID
  - Rolling conversation history (last N turns)
  - Session metadata and timing
  - Connection status
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SessionStatus(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"
    ERROR = "error"


@dataclass
class ConversationTurn:
    role: str          # "user" or "assistant"
    text: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class VoiceSession:
    """Holds all state for a single voice conversation session."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: SessionStatus = SessionStatus.CONNECTING
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    # Rolling conversation history
    conversation: list[ConversationTurn] = field(default_factory=list)

    # Realtime API session ID (assigned by Azure after session.created event)
    realtime_session_id: Optional[str] = None

    # Current in-progress response (for interruption handling)
    current_response_id: Optional[str] = None
    is_agent_speaking: bool = False

    # Metadata
    user_agent: Optional[str] = None
    remote_ip: Optional[str] = None

    # Authenticated user context (None for anonymous sessions)
    user_id: Optional[int] = None
    db_session_id: Optional[int] = None   # conversation_sessions.id

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = time.time()

    def add_turn(self, role: str, text: str, max_turns: int = 6) -> None:
        """Add a conversation turn and prune to max_turns."""
        self.conversation.append(ConversationTurn(role=role, text=text))
        if len(self.conversation) > max_turns:
            # Keep the most recent turns
            self.conversation = self.conversation[-max_turns:]
        self.touch()

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_activity

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "turn_count": len(self.conversation),
            "realtime_session_id": self.realtime_session_id,
        }


class SessionRegistry:
    """Thread-safe registry of all active sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, VoiceSession] = {}

    def create(self, **kwargs) -> VoiceSession:
        session = VoiceSession(**kwargs)
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Optional[VoiceSession]:
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def cleanup_stale(self, timeout_seconds: int = 300) -> int:
        """Remove sessions idle for longer than timeout. Returns count removed."""
        stale = [
            sid for sid, s in self._sessions.items()
            if s.idle_seconds > timeout_seconds
        ]
        for sid in stale:
            del self._sessions[sid]
        return len(stale)

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    def stats(self) -> dict:
        return {
            "active_sessions": self.active_count,
            "session_ids": list(self._sessions.keys()),
        }


# Global registry instance
session_registry = SessionRegistry()
