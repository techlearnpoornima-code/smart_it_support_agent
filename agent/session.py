"""In-memory session store with TTL-based automatic expiry."""

import time

from models.intent import SessionState


class SessionStore:
    """Thread-safe in-memory session store with TTL-based automatic expiry."""

    def __init__(self, ttl_seconds: int = 1800):
        self._sessions: dict[str, dict] = {}
        self._ttl = ttl_seconds

    def get(self, session_id: str) -> SessionState | None:
        """Retrieve a session, returning None if missing or expired."""
        record = self._sessions.get(session_id)
        if record is None:
            return None
        if time.time() - record["last_active"] > self._ttl:
            self.expire(session_id)
            return None
        return SessionState(**record["data"])

    def update(self, session_id: str, state: SessionState) -> None:
        """Persist an updated session state and refresh its TTL timestamp."""
        self._sessions[session_id] = {
            "data": state.model_dump(),
            "last_active": time.time(),
        }

    def expire(self, session_id: str) -> None:
        """Remove a session immediately, regardless of remaining TTL."""
        self._sessions.pop(session_id, None)

    def get_or_create(self, session_id: str, user_id: str) -> SessionState:
        """Return an existing session or create a new one if none exists."""
        state = self.get(session_id)
        if state is None:
            state = SessionState(session_id=session_id, user_id=user_id)
            self.update(session_id, state)
        return state

    def active_count(self) -> int:
        """Return the number of sessions that have not yet expired."""
        now = time.time()
        return sum(
            1 for r in self._sessions.values()
            if now - r["last_active"] <= self._ttl
        )
