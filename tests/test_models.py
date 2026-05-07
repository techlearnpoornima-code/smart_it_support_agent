"""Unit tests for data models, safety logic, failure detection, and fixture sanity."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.failure import FailureMode, detect_failure, failure_to_policy
from agent.safety import INTENT_PRIORITY, check_authorization, is_dangerous, resolve_primary_intent
from models.intent import IntentResult, SessionState
from models.policy import CAPABILITY_REGISTRY, ResponsePolicy
from models.slots import OPTIONAL_SLOTS, REQUIRED_SLOTS

FIXTURES = Path(__file__).parent / "fixtures"


# --- IntentResult ---

def test_intent_result_valid():
    r = IntentResult(
        intent="reset_password",
        confidence=0.95,
        slots={"system_name": "Slack"},
        missing_slots=[],
        raw_input="I need to reset my Slack password",
    )
    assert r.intent == "reset_password"
    assert r.confidence == 0.95
    assert r.is_dangerous is False


def test_intent_result_confidence_bounds():
    with pytest.raises(ValidationError):
        IntentResult(intent="reset_password", confidence=1.5,
                     slots={}, missing_slots=[], raw_input="x")
    with pytest.raises(ValidationError):
        IntentResult(intent="reset_password", confidence=-0.1,
                     slots={}, missing_slots=[], raw_input="x")


def test_intent_result_invalid_intent():
    with pytest.raises(ValidationError):
        IntentResult(intent="fly_to_moon", confidence=0.9,
                     slots={}, missing_slots=[], raw_input="x")


def test_intent_result_unknown_is_valid():
    r = IntentResult(intent="unknown", confidence=0.1, slots={}, missing_slots=[], raw_input="???")
    assert r.intent == "unknown"


# --- SessionState ---

def test_session_state_defaults():
    s = SessionState(session_id="sess_001", user_id="user_123")
    assert s.turn_count == 0
    assert s.clarification_turns == 0
    assert s.pending_intent is None
    assert s.history == []


def test_session_state_with_pending_intent():
    intent = IntentResult(
        intent="check_leave", confidence=0.9, slots={},
        missing_slots=["leave_type"], raw_input="time off"
    )
    s = SessionState(session_id="sess_002", user_id="user_456", pending_intent=intent)
    assert s.pending_intent.intent == "check_leave"
    assert s.pending_intent.missing_slots == ["leave_type"]


# --- Slots ---

def test_required_slots_coverage():
    intents = ["reset_password", "check_leave", "software_request",
               "policy_lookup", "hardware_issue"]
    for intent in intents:
        assert intent in REQUIRED_SLOTS, f"{intent} missing from REQUIRED_SLOTS"
        assert intent in OPTIONAL_SLOTS, f"{intent} missing from OPTIONAL_SLOTS"


def test_required_slots_are_lists():
    for intent, slots in REQUIRED_SLOTS.items():
        assert isinstance(slots, list), f"{intent} required slots should be a list"


# --- ResponsePolicy ---

def test_response_policy_values():
    assert ResponsePolicy.ANSWER == "answer"
    assert ResponsePolicy.CLARIFY == "clarify"
    assert ResponsePolicy.REDIRECT == "redirect"
    assert ResponsePolicy.DENY == "deny"
    assert ResponsePolicy.ESCALATE == "escalate"


# --- CapabilityRegistry ---

def test_capability_registry_supports_known_intents():
    assert CAPABILITY_REGISTRY.supports("reset_password")
    assert CAPABILITY_REGISTRY.supports("policy_lookup")
    assert not CAPABILITY_REGISTRY.supports("account_deletion")


def test_capability_registry_hitl():
    assert CAPABILITY_REGISTRY.requires_hitl("account_deletion")
    assert CAPABILITY_REGISTRY.requires_hitl("access_revocation")
    assert not CAPABILITY_REGISTRY.requires_hitl("reset_password")


# --- Safety ---

def test_is_dangerous_cross_user_reset():
    session = SessionState(session_id="s1", user_id="alice")
    assert is_dangerous("reset_password", {"username": "bob"}, session) is True


def test_is_dangerous_same_user_reset():
    session = SessionState(session_id="s1", user_id="alice")
    assert is_dangerous("reset_password", {"username": "alice"}, session) is False


def test_is_dangerous_no_username_defaults_safe():
    session = SessionState(session_id="s1", user_id="alice")
    assert is_dangerous("reset_password", {}, session) is False


def test_is_dangerous_software_cost_above_threshold():
    session = SessionState(session_id="s1", user_id="alice")
    assert is_dangerous("software_request", {"software_cost": 600}, session) is True
    assert is_dangerous("software_request", {"software_cost": 400}, session) is False


def test_is_dangerous_critical_hardware():
    session = SessionState(session_id="s1", user_id="alice")
    assert is_dangerous("hardware_issue", {"severity": "critical"}, session) is True
    assert is_dangerous("hardware_issue", {"severity": "high"}, session) is False


def test_check_authorization_same_user():
    assert check_authorization("alice", "alice", "reset_password", []) is True


def test_check_authorization_it_admin_cross_user():
    assert check_authorization("admin1", "bob", "reset_password", ["it_admin"]) is True


def test_check_authorization_cross_user_denied():
    assert check_authorization("alice", "bob", "reset_password", []) is False


def test_resolve_primary_intent_priority():
    assert resolve_primary_intent(["policy_lookup", "reset_password"]) == "reset_password"
    assert resolve_primary_intent(["check_leave", "hardware_issue"]) == "hardware_issue"
    assert resolve_primary_intent(["policy_lookup"]) == "policy_lookup"


def test_intent_priority_security_first():
    assert INTENT_PRIORITY[0] == "reset_password"
    assert INTENT_PRIORITY[-1] == "policy_lookup"


# --- Failure detection ---

def test_detect_failure_low_confidence():
    r = IntentResult(intent="unknown", confidence=0.2, slots={}, missing_slots=[], raw_input="x")
    assert detect_failure(r) == FailureMode.LOW_CONFIDENCE


def test_detect_failure_missing_slots():
    r = IntentResult(intent="check_leave", confidence=0.9, slots={},
                     missing_slots=["leave_type"], raw_input="time off")
    assert detect_failure(r) == FailureMode.MISSING_SLOTS


def test_detect_failure_dangerous_action():
    r = IntentResult(
        intent="reset_password", confidence=0.9, slots={},
        missing_slots=[], is_dangerous=True, raw_input="reset bob's password"
    )
    assert detect_failure(r) == FailureMode.DANGEROUS_ACTION


def test_detect_failure_none_on_clean_result():
    r = IntentResult(
        intent="policy_lookup", confidence=0.92,
        slots={"topic": "remote work"}, missing_slots=[], raw_input="remote work policy"
    )
    assert detect_failure(r) is None


def test_failure_to_policy_mapping():
    assert failure_to_policy(FailureMode.LOW_CONFIDENCE) == ResponsePolicy.REDIRECT
    assert failure_to_policy(FailureMode.MISSING_SLOTS) == ResponsePolicy.CLARIFY
    assert failure_to_policy(FailureMode.DANGEROUS_ACTION) == ResponsePolicy.ESCALATE
    assert failure_to_policy(FailureMode.TOOL_FAILURE) == ResponsePolicy.DENY


# --- Fixture sanity ---

def test_utterances_fixture_loads():
    data = json.loads((FIXTURES / "utterances.json").read_text())
    assert len(data) >= 25
    for item in data:
        assert "intent" in item
        assert "text" in item
        assert "expected_slots" in item


def test_adversarial_fixture_loads():
    data = json.loads((FIXTURES / "adversarial.json").read_text())
    assert len(data) >= 40
    for item in data:
        assert "text" in item
        assert "notes" in item
