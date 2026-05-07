"""Failure mode detection and policy mapping for the agent pipeline."""

from enum import StrEnum

from models.intent import IntentResult
from models.policy import ResponsePolicy

LOW_CONFIDENCE_THRESHOLD = 0.40
MEDIUM_CONFIDENCE_THRESHOLD = 0.80


class FailureMode(StrEnum):
    """The four recoverable failure states the pipeline can enter."""

    LOW_CONFIDENCE = "low_confidence"
    MISSING_SLOTS = "missing_slots"
    DANGEROUS_ACTION = "dangerous_action"
    TOOL_FAILURE = "tool_failure"


def detect_failure(result: IntentResult) -> FailureMode | None:
    """Inspect an IntentResult and return the first active failure mode, or None."""
    if result.confidence < LOW_CONFIDENCE_THRESHOLD:
        return FailureMode.LOW_CONFIDENCE
    if result.missing_slots:
        return FailureMode.MISSING_SLOTS
    if result.is_dangerous:
        return FailureMode.DANGEROUS_ACTION
    return None


def failure_to_policy(mode: FailureMode) -> ResponsePolicy:
    """Map a FailureMode to the ResponsePolicy that should be returned to the user."""
    mapping = {
        FailureMode.LOW_CONFIDENCE:   ResponsePolicy.REDIRECT,
        FailureMode.MISSING_SLOTS:    ResponsePolicy.CLARIFY,
        FailureMode.DANGEROUS_ACTION: ResponsePolicy.ESCALATE,
        FailureMode.TOOL_FAILURE:     ResponsePolicy.DENY,
    }
    return mapping[mode]


FAILURE_MESSAGES: dict[FailureMode, str] = {
    FailureMode.LOW_CONFIDENCE: (
        "I'm not sure I understood that. Could you rephrase your request?"
    ),
    FailureMode.MISSING_SLOTS: (
        "I need a bit more information to help you with that."
    ),
    FailureMode.DANGEROUS_ACTION: (
        "This action requires approval before I can proceed. "
        "Let me summarise what I'm about to do."
    ),
    FailureMode.TOOL_FAILURE: (
        "I wasn't able to complete that request. I've logged the issue — "
        "please try again or contact IT directly."
    ),
}
