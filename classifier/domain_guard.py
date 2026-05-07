"""Keyword-based domain guard — blocks off-topic and injection inputs before any LLM call."""

from models.policy import ResponsePolicy

# Phrases that indicate the request is outside IT support scope
OFF_TOPIC_PATTERNS = [
    "weather", "forecast", "flight", "book a", "poem", "recipe",
    "translate", "who is the", "what is the capital", "stock price",
    "sports score", "movie", "restaurant", "song lyrics", "music",
    "game", "news", "politics", "vote", "election", "celebrity",
    "trivia", "horoscope", "lottery", "sports team",
]

# Phrases that attempt to override or escape the agent's system instructions
INJECTION_PATTERNS = [
    "ignore previous instructions", "ignore all instructions",
    "you are now", "forget you are", "act as", "jailbreak",
    "disregard your", "new persona", "pretend you", "roleplay as",
    "do anything now", "dan mode", "override your",
    "system prompt", "reveal your instructions",
]


def check_domain(text: str) -> ResponsePolicy | None:
    """Return REDIRECT if the text is a prompt injection or off-topic request, else None.

    Injection is checked before off-topic so security concerns are always flagged first.
    This runs before any LLM call — intentionally fast, free, and deterministic.
    """
    lower = text.lower()
    if any(p in lower for p in INJECTION_PATTERNS):
        return ResponsePolicy.REDIRECT
    if any(p in lower for p in OFF_TOPIC_PATTERNS):
        return ResponsePolicy.REDIRECT
    return None
