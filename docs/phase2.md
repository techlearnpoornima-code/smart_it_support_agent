# Phase 2: The Router — LLM Classifier with Provider Plugin Architecture

> **Goal:** The LLM classifies intent and extracts slots as validated JSON. Developer can swap between Ollama, Anthropic, and OpenAI with a single `.env` change.

---

## What's New in Phase 2 (vs Phase 1)

| Concern | Phase 1 | Phase 2 |
|---|---|---|
| LLM calls | None | Yes — via pluggable provider |
| Query input | Raw user text | Rephrased for clarity first |
| Domain check | None | Keyword-based guard (fast, free) |
| Intent routing | Stub | Real `IntentResult` from LLM |
| Multi-intent | Not handled | Deferred to Phase 3 |
| Logging | Schema defined | Event-sourced — every pipeline step is a separate retraceable event |

---

## Key Design Decision: LLM Provider Plugin

The developer must be able to swap LLM providers with **one line in `.env`**:

```env
LLM_PROVIDER=ollama        # default — local, free, no key needed
LLM_PROVIDER=anthropic     # Claude Sonnet — production grade
LLM_PROVIDER=openai        # GPT-4o-mini — alternative
```

No code changes required to switch. All providers share the same abstract interface.

### Provider Plugin Structure

```
classifier/
├── providers/
│   ├── __init__.py
│   ├── base.py          # Abstract LLMProvider interface
│   ├── ollama.py        # Ollama (local, default)
│   ├── anthropic.py     # Anthropic Claude
│   ├── openai.py        # OpenAI GPT
│   └── factory.py       # get_provider() — reads LLM_PROVIDER env var
├── prompts.py           # System prompt + few-shot examples
├── domain_guard.py      # Keyword-based off-topic + injection filter
├── query_rewriter.py    # Rephrases raw user input before classification
└── llm_classifier.py   # Full pipeline: guard → rewrite → classify → validate
```

### Abstract Interface (`base.py`)

```python
class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str: ...

    @abstractmethod
    def model_name(self) -> str: ...
```

The classifier only ever calls `provider.complete(system, user)` — it never knows which provider is active.

### Default: Ollama (Local)

- Runs entirely on your machine — no API key, no cost
- Uses OpenAI-compatible endpoint: `http://localhost:11434/v1`
- Default model: `llama3.2` (configurable via `OLLAMA_MODEL`)
- Setup: `ollama pull llama3.2` before first run

### Anthropic (Production)

- Model: `claude-sonnet-4-6`
- Uses prompt caching on the system prompt (saves ~90% cost on repeated calls)
- Requires: `ANTHROPIC_API_KEY` in `.env`

### OpenAI (Alternative)

- Model: `gpt-4o-mini`
- Requires: `OPENAI_API_KEY` in `.env`

---

## Pipeline Flow

```
Raw User Input
      │
      ▼
┌──────────────────┐
│  Domain Guard    │ ── off-topic / injection? ──→ ResponsePolicy.REDIRECT
│  (keyword-based) │                                (no LLM call made)
└──────────────────┘
      │ in-domain
      ▼
┌──────────────────┐
│  Query Rewriter  │  "change slack password"
│  (LLM call)      │  → "The user wants to reset their password for the Slack platform."
└──────────────────┘
      │ rephrased text
      ▼
┌──────────────────┐
│ LLM Classifier   │ ── provider.complete(SYSTEM_PROMPT, rephrased_text)
│ (any provider)   │
└──────────────────┘
      │ raw JSON string
      ▼
┌──────────────────┐
│  JSON Validate   │ ── invalid? ──→ 1 retry with original text
│  (Pydantic)      │             ──→ return intent=unknown on 2nd failure
└──────────────────┘
      │ IntentResult
      ▼
┌──────────────────┐
│  log_event()     │ ── session_id, turn, raw_input, rephrased, result, provider, latency_ms
└──────────────────┘
      │
      ▼
   IntentResult
```

---

## 1. Domain Guard — `classifier/domain_guard.py`

**Keyword-based (Phase 2 only).** Fast, free, catches obvious cases without an LLM call.

Two checks:

### Off-topic keywords
```python
OFF_TOPIC_PATTERNS = [
    "weather", "forecast", "flight", "book a", "poem", "recipe",
    "translate", "who is the", "what is the capital", "stock price",
    "sports score", "movie", "restaurant", ...
]
```

### Prompt injection patterns
```python
INJECTION_PATTERNS = [
    "ignore previous instructions", "ignore all instructions",
    "you are now", "forget you are", "act as", "jailbreak",
    "disregard your", "new persona", ...
]
```

Returns `ResponsePolicy.REDIRECT` for either match. Otherwise returns `None` (proceed).

> **Phase 3 upgrade:** Add LLM-based domain check as a fallback for edge cases keyword matching misses.

---

## 2. Query Rewriter — `classifier/query_rewriter.py`

**Why:** Users write terse, ambiguous messages. Rephrasing into an explicit sentence improves classifier accuracy significantly.

| Raw input | Rephrased |
|---|---|
| `"change slack password"` | `"The user wants to reset their password for the Slack platform."` |
| `"laptop broken"` | `"The user is reporting a hardware issue — their laptop is not functioning properly."` |
| `"figma"` | `"The user is requesting software installation — specifically the Figma design tool."` |
| `"sick days?"` | `"The user wants to check their remaining sick leave balance."` |
| `"can't get in"` | `"The user cannot access a system and may need a password reset."` |

**Rules:**
- Uses the same `LLMProvider` as the classifier
- Short prompt: *"Rephrase as a clear, explicit IT support request. Keep it factual. Do not invent details not present in the input. One sentence only."*
- Max 60 tokens output
- Falls back to original text if rewrite fails or exceeds 3 seconds

**What the rewriter does NOT do:**
- Does not change or infer the intent
- Does not add slot values not mentioned by the user
- Does not correct factual errors

---

## 3. System Prompt — `classifier/prompts.py`

Strict JSON-only output. The LLM must return exactly this schema:

```json
{
  "intent": "reset_password",
  "confidence": 0.91,
  "slots": { "system_name": "Slack" },
  "missing_slots": []
}
```

Prompt includes:
- All 5 intent definitions + `unknown`
- Required vs optional slots per intent
- Slot inference rules (e.g. infer `username` from "my" → do NOT list in `missing_slots`)
- 2–3 few-shot examples per intent
- Instruction: *"Return ONLY the JSON object. No explanation, no markdown fences, no text before or after."*

---

## 4. LLM Classifier — `classifier/llm_classifier.py`

```python
def classify_intent(
    raw_input: str,
    session: SessionState,
    provider: LLMProvider,
) -> IntentResult:
```

Steps:
1. Truncate input to 2000 chars (security boundary)
2. `check_domain(raw_input)` — redirect if off-topic/injection
3. `rewrite_query(raw_input, provider)` — get explicit rephrased text
4. `provider.complete(SYSTEM_PROMPT, rephrased)` — get JSON string
5. Parse JSON → validate as `IntentResult` (Pydantic)
6. On `ValidationError`: retry once with original (unrephrased) text
7. On second failure: return `IntentResult(intent="unknown", confidence=0.0, ...)`
8. `log_event(...)` — log session, input, rephrased, result, provider name, latency_ms

---

## 5. Event-Sourced Logging — `logs/logger.py`

Every pipeline step is a **separate, timestamped event** linked by `event_id` → `parent_event_id`. A full conversation is retraceable and replayable from the JSONL file alone.

### Event chain for one turn

```
USER_INPUT      (evt_aaa)  ─ raw text received
  └── DOMAIN_GUARD    (evt_bbb, parent=aaa)  ─ 1ms,   result=pass
        └── QUERY_REWRITE  (evt_ccc, parent=bbb)  ─ 312ms, rephrased text
              └── CLASSIFICATION (evt_ddd, parent=ccc)  ─ 842ms, intent+slots
                    └── AGENT_RESPONSE (evt_eee, parent=ddd)  ─ response text
TURN_SUMMARY    (links all step IDs, total_duration_ms=1155)
```

### JSONL event schema

```json
{
  "event_id":        "550e8400-e29b-41d4-a716-446655440001",
  "parent_event_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp":       "2025-05-03T10:22:11+00:00",
  "session_id":      "sess_alice",
  "user_id":         "alice",
  "turn":            2,
  "event_type":      "classification",
  "provider":        "ollama",
  "data": {
    "raw_input":     "change slack password",
    "rephrased":     "The user wants to reset their Slack password.",
    "intent":        "reset_password",
    "confidence":    0.91,
    "slots":         { "system_name": "Slack" },
    "missing_slots": [],
    "retry_count":   0
  },
  "duration_ms":     842,
  "success":         true,
  "error":           null
}
```

### 18 EventTypes

`session_start` · `session_end` · `user_input` · `domain_guard` · `query_rewrite` ·
`classification` · `validation_error` · `retry` · `failure_mode` · `slot_fill` ·
`tool_call` · `tool_result` · `agent_response` · `hitl_trigger` · `hitl_decision` ·
`error` · `turn_summary`

### How to replay / retrace a session

```bash
# All events for a session in order
grep '"session_id": "sess_alice"' logs/events.jsonl | jq .

# High-level turn summaries only
grep '"event_type": "turn_summary"' logs/events.jsonl \
  | jq '{turn, intent: .data.final_intent, policy: .data.response_policy, ms: .data.total_duration_ms}'

# Trace one turn step-by-step
grep '"turn": 2' logs/events.jsonl \
  | jq '{type: .event_type, ms: .duration_ms, success, error}'
```

### `timed_event()` context manager

All classifier components use `timed_event()` to auto-measure duration and capture failures:

```python
with timed_event(EventType.CLASSIFICATION, session_id, user_id, turn,
                 data={"raw_input": text}, provider=provider.provider_name()) as ctx:
    result = provider.complete(SYSTEM_PROMPT, text)
    ctx["data"]["raw_response"] = result   # enrich data before log is written
# → logged automatically with duration_ms and success=true
# → if exception raised: success=false, error=<message> logged automatically
```

---

## 6. Evaluation Runner — `scripts/eval_classifier.py`

Runs all fixtures through the live classifier and prints a report:

```
Provider: ollama (llama3.2)
──────────────────────────────────────────────────────
Intent              Total   Correct   Accuracy   Avg Conf
reset_password        7       7        100%        0.89
check_leave           5       4         80%        0.82
software_request      5       5        100%        0.91
policy_lookup         5       5        100%        0.88
hardware_issue        5       5        100%        0.87
──────────────────────────────────────────────────────
Overall              27      26         96%        0.87

Confidence Distribution
  ≥ 0.80 (proceed):    22 / 27  (81%)
  0.40–0.79 (clarify):  4 / 27  (15%)
  < 0.40 (rephrase):    1 / 27   (4%)

Adversarial Cases (42 total)
  Correctly redirected (off-topic):   8 / 8
  Correctly flagged (dangerous):      8 / 8
  Missing slots detected:             5 / 5
  Low confidence:                     6 / 6
  Multi-intent (deferred to Phase 3): 4 / 4  ← logged, not handled yet
  Missed / incorrect:                 4 / 42  ← review these
```

Use this report to empirically adjust `LOW_CONFIDENCE_THRESHOLD` and `MEDIUM_CONFIDENCE_THRESHOLD` in `agent/failure.py`.

---

## 6. Environment Variables (updated `.env`)

```env
# Provider selection (ollama | anthropic | openai)
LLM_PROVIDER=ollama

# Ollama settings
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Anthropic settings
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6

# OpenAI settings
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

---

## Phase 2 Deliverables Checklist

- [ ] `classifier/providers/base.py` — `LLMProvider` abstract interface
- [ ] `classifier/providers/ollama.py` — Ollama (OpenAI-compatible endpoint)
- [ ] `classifier/providers/anthropic.py` — Anthropic Claude with prompt caching
- [ ] `classifier/providers/openai.py` — OpenAI GPT
- [ ] `classifier/providers/factory.py` — `get_provider()` factory function
- [ ] `classifier/prompts.py` — system prompt + few-shot examples
- [ ] `classifier/domain_guard.py` — keyword off-topic + injection filter
- [ ] `classifier/query_rewriter.py` — query rephrasing via LLM
- [ ] `classifier/llm_classifier.py` — full pipeline with retry + logging
- [ ] `scripts/eval_classifier.py` — accuracy evaluation runner
- [ ] `tests/test_classifier.py` — unit tests with mocked provider
- [ ] `main.py` (update) — replace Phase 1 stub with real classifier
- [ ] Update `CLAUDE.md` phase table to mark Phase 2 in progress

---

## Acceptance Criteria

Phase 2 is complete when:
1. `uv run pytest` passes (all tests, including mocked classifier tests)
2. `uv run python scripts/eval_classifier.py` shows ≥ 85% accuracy on utterances fixture
3. Switching `LLM_PROVIDER=anthropic` in `.env` works without code changes
4. All classifier calls logged to `logs/events.jsonl` with provider name + latency
5. `uv run python main.py` shows real intent results (not Phase 1 stub)

---

*Phase 2 complete → Phase 3: Mock tools, slot filling, clarification loop, multi-intent detection.*
