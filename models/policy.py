"""Response policy enum and capability registry for intent routing."""

from dataclasses import dataclass, field
from enum import StrEnum


class ResponsePolicy(StrEnum):
    """Enumeration of the agent's possible response strategies."""

    ANSWER = "answer"
    CLARIFY = "clarify"
    REDIRECT = "redirect"
    DENY = "deny"
    ESCALATE = "escalate"


@dataclass
class CapabilityRegistry:
    """Declares which intents the agent can answer, execute, or must escalate."""

    can_answer: list[str] = field(default_factory=lambda: [
        "policy_lookup",
        "check_leave",
    ])
    can_execute: list[str] = field(default_factory=lambda: [
        "reset_password",
        "software_request",
        "hardware_issue",
    ])
    cannot_execute: list[str] = field(default_factory=lambda: [
        "account_deletion",
        "access_revocation",
    ])

    def supports(self, intent: str) -> bool:
        """Return True if the intent is in the answer or execute list."""
        return intent in self.can_answer or intent in self.can_execute

    def requires_hitl(self, intent: str) -> bool:
        """Return True if the intent requires human-in-the-loop confirmation."""
        return intent in self.cannot_execute


CAPABILITY_REGISTRY = CapabilityRegistry()
