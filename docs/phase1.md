# Phase 1: The Foundation — Everything Before LLM Code

> **Rule:** No LLM calls until this phase is complete. Every bug in an agentic system traces back to ambiguous data — define the contract first.

---

## Goals

- Define the data contract every component will respect
- Scaffold the full project structure
- Write all Pydantic models, enums, and config
- Establish session management, safety rules, failure taxonomy, and logging
- Create test fixtures (normal + adversarial utterances)

**Phase 1 ends when:** you can import all models, run `pytest`, and the data contract is 100% solid.

---

## 1. Project Setup

- Initialize with `uv` (`pyproject.toml`, `.python-version`, virtual env)
- Folder structure matching `requirement_analysis.md § 14`
- `.gitignore` — exclude `logs/`, `.env`, `__pycache__/`, `.venv/`
- `.env` — holds `ANTHROPIC_API_KEY`

### Folder Structure

```
smart_it_support_agent/
├── models/
│   ├── intent.py          # IntentResult, SessionState
│   ├── slots.py           # Per-intent slot schemas
│   └── policy.py          # ResponsePolicy enum, CapabilityRegistry
├── classifier/
│   └── llm_classifier.py  # Phase 2: LLM JSON prompt + validation
├── tools/
│   ├── mock_tools.py      # Phase 3: mock implementations
│   └── real_tools.py      # Phase 4: real API calls
├── agent/
│   ├── session.py         # SessionStore (get, update, expire)
│   ├── slot_filler.py     # Phase 3: clarification loop
│   ├── safety.py          # DANGEROUS_ACTIONS, check_authorization
│   └── failure.py         # FailureMode enum + handler stubs
├── rag/
│   └── policy_search.py   # Phase 4: ChromaDB + RAG pipeline
├── logs/
│   ├── logger.py          # JSONL append utility
│   └── events.jsonl       # Append-only log (gitignored)
├── tests/
│   ├── test_models.py     # Validate Pydantic schemas
│   ├── test_session.py    # SessionStore unit tests
│   └── fixtures/
│       ├── utterances.json    # 10-15 examples × 5 intents
│       └── adversarial.json   # 50 edge cases
├── .env
├── .gitignore
├── pyproject.toml
└── main.py                # CLI entrypoint
```

---

## 2. Data Contracts — `models/`

### `models/intent.py`

**`IntentResult`** — the single source of truth for every classifier output:

| Field | Type | Purpose |
|---|---|---|
| `intent` | Literal (5 intents + `unknown`) | Classified intent |
| `confidence` | float 0.0–1.0 | LLM self-reported score (calibrate empirically) |
| `slots` | dict | Extracted parameters |
| `missing_slots` | list[str] | Slots still needed from user |
| `is_dangerous` | bool | Triggers HITL flow |
| `raw_input` | str | Original user message (for logging) |

**`SessionState`** — per-session memory:

| Field | Type | Purpose |
|---|---|---|
| `session_id` | str | Unique identifier |
| `user_id` | str | Authenticated user — never trust from message |
| `turn_count` | int | Total conversation turns |
| `clarification_turns` | int | Turns asking for slots (hard cap: 2) |
| `pending_intent` | Optional[IntentResult] | Last intent awaiting completion |
| `history` | list[dict] | Full conversation for LLM context |

### `models/slots.py`

Per-intent slot schemas:

| Intent | Required Slots | Optional Slots |
|---|---|---|
| `reset_password` | `system_name`, `username` | — |
| `check_leave` | `leave_type` | `date_range` |
| `software_request` | `software_name`, `reason` | `urgency` |
| `policy_lookup` | `topic` | — |
| `hardware_issue` | `device_id`, `description` | `severity` |

### `models/policy.py`

**`ResponsePolicy` enum** (from `agent_policy.md`):

```
ANSWER     → LLM generates a grounded response
CLARIFY    → Agent asks for missing slot or disambiguation
REDIRECT   → Off-topic: politely redirect to supported domain
DENY       → Unsupported or unauthorized action
ESCALATE   → Human-in-the-loop required
```

**`CapabilityRegistry`** — explicit agent boundaries:

```
can_answer:       policy_lookup, check_leave (informational)
can_execute:      reset_password, software_request, hardware_issue
cannot_execute:   account_deletion, access_revocation (always HITL)
```

---

## 3. Session Store — `agent/session.py`

`SessionStore` class with:
- `get(session_id)` → returns session data or `None` if expired
- `update(session_id, data)` → upserts with fresh `last_active` timestamp
- `expire(session_id)` → explicit eviction

**TTL:** 30 minutes of inactivity (configurable via `ttl_seconds`).

---

## 4. Safety Config — `agent/safety.py`

### DANGEROUS_ACTIONS

```python
DANGEROUS_ACTIONS = {
    "reset_password":   lambda slots, ctx: slots.get("username") != ctx.user_id,
    "software_request": lambda slots, ctx: slots.get("software_cost", 0) > 500,
    "hardware_issue":   lambda slots, ctx: slots.get("severity") == "critical",
    "account_deletion": lambda slots, ctx: True,  # always HITL
}
```

### Multi-Intent Priority Order

```
security > hardware > software > leave > policy
```

When multiple intents detected: address highest priority first, surface others.

### Authorization Check

```python
check_authorization(requesting_user_id, target_user_id, action, user_roles) -> bool
```

- Same user → always allowed
- IT admin + `reset_password` → allowed
- All other cross-user actions → denied

---

## 5. Failure Mode Taxonomy — `agent/failure.py`

Exactly 4 failure modes. Each has a distinct response path.

| Mode | Condition | Agent Response |
|---|---|---|
| `LOW_CONFIDENCE` | `confidence < 0.40` | *"I'm not sure I understood. Could you rephrase?"* |
| `MISSING_SLOTS` | `len(missing_slots) > 0` | Ask for slot (max 2 turns, then `ESCALATE`) |
| `DANGEROUS_ACTION` | `is_dangerous == True` | Generate summary → HITL → wait for confirm/cancel |
| `TOOL_FAILURE` | API error / timeout | *"I wasn't able to complete that. I've logged the issue."* |

---

## 6. Logging — `logs/logger.py`

JSONL schema (one object per line, append-only):

```json
{
  "timestamp": "2025-05-03T10:22:11Z",
  "session_id": "sess_abc123",
  "user_id": "user_456",
  "turn": 2,
  "raw_input": "I need to reset my Slack password",
  "intent_result": {
    "intent": "reset_password",
    "confidence": 0.91,
    "slots": { "system_name": "Slack" },
    "missing_slots": [],
    "is_dangerous": false
  },
  "tool_called": "auth_service.reset",
  "tool_result": "success",
  "latency_ms": 842
}
```

Log **every** input — including failed, ambiguous, and off-topic ones. These are the most valuable for future BERT training.

---

## 7. Test Fixtures — `tests/fixtures/`

### `utterances.json`
10–15 examples × 5 intents covering normal usage.

### `adversarial.json`
50 edge cases including:
- Cross-user action → should trigger HITL
- `"I can't get into anything"` → low confidence
- Multi-intent message → priority routing applied
- `"what's the policy on resetting passwords"` → `policy_lookup`, NOT `reset_password`
- Missing required slot → clarification loop triggered
- Off-topic input → domain guardrail redirects

---

## Phase 1 Deliverables Checklist

- [ ] `pyproject.toml` + uv setup
- [ ] Full folder scaffold
- [ ] `models/intent.py` — `IntentResult`, `SessionState`
- [ ] `models/slots.py` — per-intent slot schemas
- [ ] `models/policy.py` — `ResponsePolicy`, `CapabilityRegistry`
- [ ] `agent/session.py` — `SessionStore`
- [ ] `agent/safety.py` — `DANGEROUS_ACTIONS`, `check_authorization`
- [ ] `agent/failure.py` — `FailureMode` enum + handler stubs
- [ ] `logs/logger.py` — JSONL append utility
- [ ] `tests/fixtures/utterances.json`
- [ ] `tests/fixtures/adversarial.json`
- [ ] `tests/test_models.py` — import + validation tests
- [ ] `tests/test_session.py` — SessionStore unit tests
- [ ] `main.py` — CLI stub

---

*Phase 1 complete when: all imports succeed, `pytest` passes, no LLM calls made.*
