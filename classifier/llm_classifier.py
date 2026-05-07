"""Full classification pipeline: domain guard → query rewrite → LLM classify → validate → log."""

import json

from pydantic import ValidationError

from classifier.domain_guard import check_domain
from classifier.prompts import CLASSIFIER_SYSTEM_PROMPT
from classifier.providers.base import LLMProvider
from classifier.query_rewriter import rewrite_query
from logs.logger import EventType, log, timed_event
from models.intent import IntentResult, SessionState
from models.policy import ResponsePolicy

_MAX_INPUT_CHARS = 2000


def _parse(raw_json: str, raw_input: str) -> IntentResult:
    """Parse the LLM's raw JSON string into a validated IntentResult."""
    data = json.loads(raw_json)
    data["raw_input"] = raw_input
    return IntentResult(**data)


def classify_intent(
    raw_input: str,
    session: SessionState,
    provider: LLMProvider,
) -> IntentResult:
    """Run the full classification pipeline and return a validated IntentResult.

    Pipeline: truncate → domain guard → query rewrite → LLM classify → Pydantic validate.
    On JSON/validation failure, retries once with the original (unrephrased) text.
    All steps are logged as separate timed events linked by session_id and turn.
    """
    raw_input = raw_input[:_MAX_INPUT_CHARS]
    sid = session.session_id
    uid = session.user_id
    turn = session.turn_count
    pname = provider.provider_name()

    # Step 1: domain guard — fast keyword check, no LLM call
    with timed_event(EventType.DOMAIN_GUARD, sid, uid, turn,
                     data={"raw_input": raw_input}) as ctx:
        guard = check_domain(raw_input)
        ctx["data"]["result"] = "redirect" if guard else "pass"

    if guard == ResponsePolicy.REDIRECT:
        return IntentResult(
            intent="unknown",
            confidence=0.0,
            slots={},
            missing_slots=[],
            raw_input=raw_input,
        )

    # Step 2: rephrase for clarity — timed QUERY_REWRITE event logged inside rewrite_query
    rephrased = rewrite_query(raw_input, provider, session_id=sid, user_id=uid, turn=turn)

    # Step 3: classify — one retry with original text on parse failure
    for attempt, text in enumerate([rephrased, raw_input]):
        event_type = EventType.CLASSIFICATION if attempt == 0 else EventType.RETRY
        raw_json: str | None = None

        try:
            with timed_event(event_type, sid, uid, turn,
                             data={"raw_input": raw_input, "text_used": text},
                             provider=pname) as ctx:
                raw_json = provider.complete(CLASSIFIER_SYSTEM_PROMPT, text)
                ctx["data"]["raw_response"] = raw_json
        except Exception:
            # provider call failed; timed_event already logged success=False
            if attempt == 1:
                break
            continue

        try:
            result = _parse(raw_json, raw_input)
            return result
        except (json.JSONDecodeError, ValidationError) as exc:
            log(EventType.VALIDATION_ERROR, sid, uid, turn,
                data={"attempt": attempt, "raw_response": raw_json, "error": str(exc)},
                provider=pname)
            if attempt == 1:
                break

    return IntentResult(
        intent="unknown",
        confidence=0.0,
        slots={},
        missing_slots=[],
        raw_input=raw_input,
    )
