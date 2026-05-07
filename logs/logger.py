"""
Event-sourced structured logger.

Every pipeline step is logged as a discrete event with a unique ID and an
optional parent link. Given a session_id, the full conversation can be
reconstructed step-by-step — every decision the agent made is retraceable
and every turn is replayable.

Log file: logs/events.jsonl  (one JSON object per line, append-only)

Event chain for a single turn:
  USER_INPUT
    └── DOMAIN_GUARD
          └── QUERY_REWRITE
                └── CLASSIFICATION
                      └── FAILURE_MODE  (if any)
                            └── TOOL_CALL
                                  └── TOOL_RESULT
                                        └── AGENT_RESPONSE
  TURN_SUMMARY  (written last, links all step IDs)
"""

import json
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from time import monotonic
from typing import Any

LOG_PATH = Path(__file__).parent / "events.jsonl"
_LOG_LOCK = threading.Lock()  # guards concurrent writes from background threads


class EventType(StrEnum):
    """All discrete event types emitted by the agent pipeline."""

    # Session lifecycle
    SESSION_START   = "session_start"
    SESSION_END     = "session_end"

    # Per-turn pipeline steps (in execution order)
    USER_INPUT      = "user_input"
    DOMAIN_GUARD    = "domain_guard"
    QUERY_REWRITE   = "query_rewrite"
    CLASSIFICATION  = "classification"
    VALIDATION_ERROR = "validation_error"
    RETRY           = "retry"
    FAILURE_MODE    = "failure_mode"
    SLOT_FILL       = "slot_fill"
    TOOL_CALL       = "tool_call"
    TOOL_RESULT     = "tool_result"
    AGENT_RESPONSE  = "agent_response"

    # Safety
    HITL_TRIGGER    = "hitl_trigger"
    HITL_DECISION   = "hitl_decision"

    # Cross-cutting
    ERROR           = "error"

    # Written after all steps complete — links the full turn together
    TURN_SUMMARY    = "turn_summary"


def _write(entry: dict) -> None:
    with _LOG_LOCK:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")


def log(
    event_type: EventType,
    session_id: str,
    user_id: str,
    turn: int,
    data: dict[str, Any],
    *,
    parent_event_id: str | None = None,
    duration_ms: int | None = None,
    success: bool = True,
    error: str | None = None,
    provider: str | None = None,
) -> str:
    """
    Log a single pipeline event. Returns event_id so callers can set
    parent_event_id on downstream events.
    """
    event_id = str(uuid.uuid4())
    _write({
        "event_id":        event_id,
        "parent_event_id": parent_event_id,
        "timestamp":       datetime.now(UTC).isoformat(),
        "session_id":      session_id,
        "user_id":         user_id,
        "turn":            turn,
        "event_type":      str(event_type),
        "provider":        provider,
        "data":            data,
        "duration_ms":     duration_ms,
        "success":         success,
        "error":           error,
    })
    return event_id


@contextmanager
def timed_event(
    event_type: EventType,
    session_id: str,
    user_id: str,
    turn: int,
    data: dict[str, Any],
    *,
    parent_event_id: str | None = None,
    provider: str | None = None,
):
    """
    Context manager that measures wall-clock duration and logs the event on
    exit — success or exception.

    Callers may mutate ctx["data"] inside the block to enrich the log entry
    before it is written:

        with timed_event(EventType.CLASSIFICATION, ..., data={"raw": text}) as ctx:
            result = provider.complete(system, text)
            ctx["data"]["intent"] = result.intent   # added before log write
    """
    ctx: dict[str, Any] = {"data": data}
    start = monotonic()
    try:
        yield ctx
        duration_ms = int((monotonic() - start) * 1000)
        log(event_type, session_id, user_id, turn,
            data=ctx["data"],
            parent_event_id=parent_event_id,
            duration_ms=duration_ms,
            success=True,
            provider=provider)
    except Exception as exc:
        duration_ms = int((monotonic() - start) * 1000)
        log(event_type, session_id, user_id, turn,
            data=ctx["data"],
            parent_event_id=parent_event_id,
            duration_ms=duration_ms,
            success=False,
            error=str(exc),
            provider=provider)
        raise


# ---------------------------------------------------------------------------
# Convenience helpers — one per common event type
# ---------------------------------------------------------------------------

def log_session_start(session_id: str, user_id: str, provider: str) -> str:
    """Emit a SESSION_START event and return its event_id."""
    return log(EventType.SESSION_START, session_id, user_id, turn=0,
               data={"provider": provider}, provider=provider)


def log_session_end(session_id: str, user_id: str, turn: int) -> str:
    """Emit a SESSION_END event recording total turns and return its event_id."""
    return log(EventType.SESSION_END, session_id, user_id, turn=turn,
               data={"total_turns": turn})


def log_user_input(session_id: str, user_id: str, turn: int,
                   raw_input: str) -> str:
    """Emit a USER_INPUT event capturing the raw text and return its event_id."""
    return log(EventType.USER_INPUT, session_id, user_id, turn=turn,
               data={"raw_input": raw_input})


def log_turn_summary(
    session_id: str,
    user_id: str,
    turn: int,
    *,
    raw_input: str,
    rephrased_input: str | None,
    final_intent: str,
    response_policy: str,
    agent_response: str,
    pipeline_step_ids: list[str],
    total_duration_ms: int,
    provider: str | None = None,
) -> str:
    """Emit a TURN_SUMMARY event linking all pipeline step IDs for the turn."""
    return log(
        EventType.TURN_SUMMARY, session_id, user_id, turn,
        data={
            "raw_input":          raw_input,
            "rephrased_input":    rephrased_input,
            "final_intent":       final_intent,
            "response_policy":    response_policy,
            "agent_response":     agent_response,
            "pipeline_step_ids":  pipeline_step_ids,  # ordered list of event_ids
            "total_duration_ms":  total_duration_ms,
        },
        provider=provider,
    )
