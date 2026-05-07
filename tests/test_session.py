"""Unit tests for SessionStore CRUD operations, TTL expiry, and state persistence."""

import time
from unittest.mock import patch

import pytest

from agent.session import SessionStore
from models.intent import IntentResult, SessionState


@pytest.fixture
def store():
    return SessionStore(ttl_seconds=60)


def test_get_or_create_new_session(store):
    state = store.get_or_create("sess_001", "user_alice")
    assert state.session_id == "sess_001"
    assert state.user_id == "user_alice"
    assert state.turn_count == 0


def test_get_or_create_returns_existing(store):
    state = store.get_or_create("sess_001", "user_alice")
    state.turn_count = 3
    store.update("sess_001", state)
    fetched = store.get_or_create("sess_001", "user_alice")
    assert fetched.turn_count == 3


def test_update_and_get(store):
    state = SessionState(session_id="sess_002", user_id="user_bob", turn_count=5)
    store.update("sess_002", state)
    fetched = store.get("sess_002")
    assert fetched is not None
    assert fetched.turn_count == 5
    assert fetched.user_id == "user_bob"


def test_get_nonexistent_returns_none(store):
    assert store.get("does_not_exist") is None


def test_expire_removes_session(store):
    state = SessionState(session_id="sess_003", user_id="user_carol")
    store.update("sess_003", state)
    assert store.get("sess_003") is not None
    store.expire("sess_003")
    assert store.get("sess_003") is None


def test_expire_nonexistent_is_safe(store):
    store.expire("ghost_session")


def test_session_expires_after_ttl(store):
    state = SessionState(session_id="sess_004", user_id="user_dave")
    store.update("sess_004", state)
    with patch("agent.session.time") as mock_time:
        mock_time.time.return_value = time.time() + 61
        assert store.get("sess_004") is None


def test_session_valid_before_ttl(store):
    state = SessionState(session_id="sess_005", user_id="user_eve")
    store.update("sess_005", state)
    with patch("agent.session.time") as mock_time:
        mock_time.time.return_value = time.time() + 30
        assert store.get("sess_005") is not None


def test_active_count(store):
    store.update("s1", SessionState(session_id="s1", user_id="u1"))
    store.update("s2", SessionState(session_id="s2", user_id="u2"))
    assert store.active_count() == 2
    store.expire("s1")
    assert store.active_count() == 1


def test_session_preserves_pending_intent(store):
    intent = IntentResult(
        intent="check_leave", confidence=0.88,
        slots={}, missing_slots=["leave_type"], raw_input="I want time off"
    )
    state = SessionState(session_id="sess_006", user_id="user_frank", pending_intent=intent)
    store.update("sess_006", state)
    fetched = store.get("sess_006")
    assert fetched.pending_intent is not None
    assert fetched.pending_intent.intent == "check_leave"
    assert fetched.pending_intent.missing_slots == ["leave_type"]


def test_clarification_turns_persisted(store):
    state = store.get_or_create("sess_007", "user_grace")
    state.clarification_turns = 2
    store.update("sess_007", state)
    fetched = store.get("sess_007")
    assert fetched.clarification_turns == 2
