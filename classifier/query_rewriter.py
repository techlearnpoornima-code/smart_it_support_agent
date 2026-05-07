"""Query rewriter — rephrases terse user input into an explicit IT support sentence."""

import concurrent.futures

from classifier.prompts import REWRITER_SYSTEM_PROMPT
from classifier.providers.base import LLMProvider
from logs.logger import EventType, timed_event

_TIMEOUT_SECONDS = 3.0  # rewrite is best-effort; classifier must not stall waiting for it


def rewrite_query(
    raw_input: str,
    provider: LLMProvider,
    *,
    session_id: str = "",
    user_id: str = "",
    turn: int = 0,
) -> str:
    """Rephrase raw_input into a clear sentence; falls back to the original on any failure.

    Runs in a thread so a hard wall-clock timeout can be enforced without blocking the
    main pipeline. Any failure — network error, empty response, timeout — returns the
    original text unchanged so the classifier can still proceed.
    When session_id is provided, logs a timed QUERY_REWRITE event with LLM latency and output.
    """
    def _call() -> str:
        if session_id:
            with timed_event(
                EventType.QUERY_REWRITE, session_id, user_id, turn,
                data={"raw_input": raw_input},
                provider=provider.provider_name(),
            ) as ctx:
                raw = provider.complete(REWRITER_SYSTEM_PROMPT, raw_input).strip()
                rephrased = raw if raw else raw_input
                ctx["data"]["rephrased"] = rephrased
            return rephrased
        raw = provider.complete(REWRITER_SYSTEM_PROMPT, raw_input).strip()
        return raw if raw else raw_input

    # Use shutdown(wait=False) so a slow LLM call does not block past the timeout
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_call)
    try:
        result = future.result(timeout=_TIMEOUT_SECONDS)
        return result
    except Exception:
        return raw_input
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
