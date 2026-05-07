# Smart IT Support Agent — Claude Code Context

## Project Overview

A production-grade agentic AI system that accepts free-form natural language from employees and routes requests to the correct IT backend tool — reliably, safely, and with graceful handling of ambiguity.

**Key design principle:** The LLM is one component inside a governed decision pipeline, not the sole decision-maker.

Pipeline: `User Input → Intent Classification → Scope Validation → Permission Check → Policy Selection → Tool Decision → Response`

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Claude Sonnet via Anthropic SDK (`anthropic`) |
| Orchestration | PydanticAI |
| Data validation | Pydantic v2 |
| Vector DB | ChromaDB (local) |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`) |
| Session state | In-memory dict (Phase 1–3) → Redis (Phase 4) |
| Logging | JSONL append-only (`logs/events.jsonl`) |
| CLI | Rich |
| Testing | pytest + pytest-asyncio |
| Package manager | uv |
| Linter | ruff |

---

## Project Phases

| Phase | Goal | Status |
|---|---|---|
| Phase 1 | Data contracts, models, session, safety, fixtures | ✅ Complete |
| Phase 2 | LLM classifier, provider plugin, query rewriter, domain guard | ✅ Complete |
| Phase 3 | Mock tools, slot filling, clarification loop, multi-intent | ⏳ Pending |
| Phase 4 | Safety guards + RAG + real APIs + HITL | ⏳ Pending |

---

## Key Files

```
models/intent.py       — IntentResult, SessionState (data contract — read this first)
models/slots.py        — Per-intent slot schemas
models/policy.py       — ResponsePolicy enum, CapabilityRegistry
agent/session.py       — SessionStore with 30-min TTL
agent/safety.py        — DANGEROUS_ACTIONS, check_authorization, multi-intent priority
agent/failure.py       — FailureMode enum + handler stubs
logs/logger.py         — JSONL structured logger
classifier/llm_classifier.py — Phase 2: LLM JSON classifier
tools/mock_tools.py    — Phase 3: mock tool implementations
rag/policy_search.py   — Phase 4: ChromaDB RAG pipeline
tests/fixtures/        — utterances.json (normal) + adversarial.json (edge cases)
docs/phase1.md         — Phase 1 detailed spec
docs/requirement_analysis.md — Full requirements
docs/agent_policy.md   — Enterprise agent policy blueprint
```

---

## Intents & Slots

| Intent | Required Slots | Dangerous? |
|---|---|---|
| `reset_password` | `system_name`, `username` | If username ≠ logged-in user |
| `check_leave` | `leave_type` | No |
| `software_request` | `software_name`, `reason` | If cost > $500 |
| `policy_lookup` | `topic` | No |
| `hardware_issue` | `device_id`, `description` | If severity = critical |

---

## Confidence Thresholds

| Confidence | Action |
|---|---|
| ≥ 0.80 | Proceed normally |
| 0.40–0.79 | Ask disambiguation question |
| < 0.40 | Ask user to rephrase |

---

## Failure Modes (exactly 4)

1. `LOW_CONFIDENCE` — confidence < 0.40 → ask to rephrase
2. `MISSING_SLOTS` — missing_slots not empty → clarify (max 2 turns, then escalate)
3. `DANGEROUS_ACTION` — is_dangerous = True → HITL confirmation
4. `TOOL_FAILURE` — API error/timeout → graceful fallback + log

---

## Development Commands

```bash
uv sync                          # Install dependencies
uv run pytest                    # Run all tests
uv run pytest tests/test_models.py -v   # Run a specific test file
uv run ruff check .              # Lint
uv run ruff format .             # Format
uv run python main.py            # Run the agent CLI
```

---

## Coding Conventions

- **Always validate LLM output** against `IntentResult` before passing downstream
- **Log every input** — including failed, ambiguous, off-topic (most valuable for training)
- **Never trust user-supplied `username`** — always use `session.user_id`
- **Never skip the safety check** — call `check_authorization()` before every tool execution
- **Clarification cap: 2 turns** — `SessionState.clarification_turns` must never exceed 2
- **Slot inference first** — infer slots from session before asking the user
- **No LLM calls in Phase 1** — data contract must be solid before any generation code

---

## Comment Standard

Every module, class, and non-trivial function must have a docstring. Inline comments explain WHY, never WHAT.

| Location | Rule |
|---|---|
| Module | One-line docstring at the top of every file describing its role in the pipeline |
| Public class | One-line docstring describing what the class represents |
| Public function | One-line docstring for any non-trivial function; omit for trivial getters |
| Inline `#` comment | Only for hidden constraints, retry logic, security boundaries, timeout rationale |

**Never write:**
- Multi-paragraph docstrings or multi-line `#` blocks
- Comments that restate the code (`# return the model` above `return self._model`)
- Task-reference comments (`# added for Phase 2`, `# called by main.py`)
- Redundant comments on trivial one-liners

---

## Environment Variables

```
ANTHROPIC_API_KEY=your_key_here   # Required for Phase 2+
```

Set in `.env` (gitignored). Load with `python-dotenv`.

---

## Rules for Claude

- Read `models/intent.py` before touching any agent or classifier code
- Read `docs/requirement_analysis.md` for full context on any new feature
- Read `docs/agent_policy.md` before adding new agent behaviors
- Never modify `logs/events.jsonl` directly — it is append-only, written by `logs/logger.py`
- Always run `uv run pytest` after changes to models or session store
- Follow the 4-phase roadmap — do not add Phase 4 features in Phase 1/2
- Present facts (callers, purpose, data structure) before creating new files
