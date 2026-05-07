# Smart IT Support Agent

A production-grade agentic AI system that accepts free-form natural language from employees and routes requests to the correct IT backend tool — reliably, safely, and with graceful handling of ambiguity.

## Architecture

```
User Input → Intent Classification → Scope Validation → Permission Check → Policy Selection → Tool Decision → Response
```

The LLM is one component inside a governed decision pipeline, not the sole decision-maker.

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Claude Sonnet via Anthropic SDK |
| Orchestration | PydanticAI |
| Data validation | Pydantic v2 |
| Vector DB | ChromaDB (local) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Session state | In-memory (Phase 1–3) → Redis (Phase 4) |
| Logging | JSONL append-only (`logs/events.jsonl`) |
| CLI | Rich |
| Testing | pytest + pytest-asyncio |
| Package manager | uv |

## Project Phases

| Phase | Goal | Status |
|---|---|---|
| Phase 1 | Data contracts, models, session, safety, fixtures | ✅ Complete |
| Phase 2 | LLM classifier, query rewriter, domain guard, logging | ✅ Complete |
| Phase 3 | Mock tools, slot filling, clarification loop, multi-intent | ⏳ Pending |
| Phase 4 | Safety guards + RAG + real APIs + HITL | ⏳ Pending |

## Supported Intents

| Intent | Description |
|---|---|
| `reset_password` | Reset or recover access credentials for a system |
| `check_leave` | Check personal leave balance or remaining days |
| `software_request` | Request installation of or access to a software tool |
| `policy_lookup` | Look up a company policy or HR guideline |
| `hardware_issue` | Report a broken or malfunctioning device |

## Setup

```bash
# Install dependencies
uv sync

# Set your API key
cp .env.example .env
# Edit .env and add ANTHROPIC_API_KEY=your_key_here

# Run the agent
uv run python main.py

# Run tests
uv run pytest

# Lint
uv run ruff check .
```

## Key Files

```
models/intent.py            — IntentResult, SessionState (data contract)
classifier/llm_classifier.py — LLM-based intent classification pipeline
classifier/query_rewriter.py — Normalises ambiguous input before classification
agent/session.py            — Session store with 30-minute TTL
agent/safety.py             — Authorization checks and HITL triggers
logs/logger.py              — Event-sourced JSONL structured logger
scripts/eval_classifier.py  — Offline evaluation against labelled utterances
tests/fixtures/utterances.json — Labelled test cases
```

## Environment Variables

```
ANTHROPIC_API_KEY=your_key_here   # Required for Phase 2+
```
