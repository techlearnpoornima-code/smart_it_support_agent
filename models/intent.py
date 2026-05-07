"""Data contracts for intent classification results and session state."""

from typing import Literal

from pydantic import BaseModel, Field


class IntentResult(BaseModel):
    """Validated output from the LLM classifier for a single user turn."""

    intent: Literal[
        "reset_password",
        "check_leave",
        "software_request",
        "policy_lookup",
        "hardware_issue",
        "unknown",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    slots: dict = Field(default_factory=dict)
    missing_slots: list[str] = Field(default_factory=list)
    is_dangerous: bool = False
    raw_input: str


class SessionState(BaseModel):
    """Per-session mutable state tracked across conversation turns."""

    session_id: str
    user_id: str
    turn_count: int = 0
    clarification_turns: int = 0
    pending_intent: IntentResult | None = None
    history: list[dict] = Field(default_factory=list)
