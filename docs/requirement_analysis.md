# Smart IT Support Agent — Requirements Analysis

> A production-grade agentic AI system that bridges natural language requests to structured IT operations. This document covers architecture, features, technical stack, roadmap, risks, and implementation guidance.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Intent & Tool Map](#2-intent--tool-map)
3. [Data Contract](#3-data-contract)
4. [Agent Behaviors](#4-agent-behaviors)
5. [Technical Stack](#5-technical-stack)
6. [Architecture Overview](#6-architecture-overview)
7. [Project Roadmap](#7-project-roadmap)
8. [Risk Register](#8-risk-register)
9. [Session & State Management](#9-session--state-management)
10. [Logging Requirements](#10-logging-requirements)
11. [Safety & Security Requirements](#11-safety--security-requirements)
12. [Intent Classifier Decision](#12-intent-classifier-decision)
13. [Failure Mode Taxonomy](#13-failure-mode-taxonomy)
14. [First Day of Code](#14-first-day-of-code)

---

## 1. Project Overview

### Goal
Build a Smart IT Support Agent that accepts free-form natural language from employees and routes requests to the correct backend tool — reliably, safely, and with graceful handling of ambiguity.

### What makes this "production-grade"
- It does not fail silently on missing information — it asks.
- It does not act on ambiguous requests — it clarifies.
- It does not perform dangerous actions without authorization — it escalates.
- Every input and output is logged for auditing and future model improvement.

### Core Challenge
Bridging the gap between a user's **messy natural language** and a rigid API's **strict parameter requirements**.

---

## 2. Intent & Tool Map

The routing table is the heart of the system. Every intent has a strict schema — not just "what parameters do I need?" but "what does missing look like vs. ambiguous vs. dangerous?"

| Intent | Required Slots | Optional Slots | Tool / API Action | Dangerous? |
|---|---|---|---|---|
| `reset_password` | `system_name`, `username` | — | `auth_service.reset()` | If `username` ≠ logged-in user |
| `check_leave` | `leave_type` | `date_range` | `hr_portal.get_balance()` | No |
| `software_request` | `software_name`, `reason` | `urgency` | `jira.create_ticket()` | If high-cost software |
| `policy_lookup` | `topic` | — | `vector_db.search()` (RAG) | No |
| `hardware_issue` | `device_id`, `description` | `severity` | `it_inventory.log_fault()` | No |

### Slot inference rules
Before asking a user for a slot, check if it can be inferred:

- `username` → default to the currently authenticated user
- `device_id` → look up from the user's registered asset list
- `leave_type` → if context contains "sick" or "vacation", infer it

---

## 3. Data Contract

Define this **before writing any LLM code**. Every bug in an agentic system traces back to ambiguous data.

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

class IntentResult(BaseModel):
    intent: Literal[
        "reset_password",
        "check_leave",
        "software_request",
        "policy_lookup",
        "hardware_issue",
        "unknown"
    ]
    confidence: float = Field(ge=0.0, le=1.0)   # 0.0 – 1.0
    slots: dict                                   # extracted parameters
    missing_slots: list[str]                      # slots that still need asking
    is_dangerous: bool = False                    # requires HITL confirmation
    raw_input: str                                # original user message

class SessionState(BaseModel):
    session_id: str
    user_id: str
    turn_count: int = 0
    clarification_turns: int = 0
    pending_intent: Optional[IntentResult] = None
    history: list[dict] = []
```

---

## 4. Agent Behaviors

### 4.1 Slot Filling (Clarification)

When a required slot is missing, the agent asks — but with constraints:

- **Maximum 2 clarification turns** before escalating to a human agent.
- **Batch questions** when multiple slots are missing: *"I need two things: which system, and for which account?"*
- **Never ask for inferrable slots** — if `username` defaults to the logged-in user, don't ask for it.

```
User:  "I need to reset my password"
Agent: "Which system are you locked out of? (e.g. Slack, Email, VPN)"
User:  "Slack"
Agent: "Got it — resetting your Slack password now."
```

### 4.2 Confidence Thresholds

| Confidence | Action |
|---|---|
| ≥ 0.80 | Proceed normally |
| 0.40 – 0.79 | Ask disambiguation question: *"Are you trying to X or Y?"* |
| < 0.40 | Say: *"I'm not sure I understood. Could you rephrase?"* |

> **Important:** LLM self-reported confidence scores are poorly calibrated. Set thresholds empirically by running a labelled test set — do not trust the raw number.

### 4.3 Human-in-the-Loop (HITL)

Trigger a human review step for:

- Any action affecting a **different user's account** (e.g., admin resetting someone else's password)
- **High-cost hardware or software** requests (above a configurable threshold)
- **Account deletion or access revocation**
- Any action where confidence < 0.40 after two clarification attempts

HITL flow:
1. Agent generates a plain-language **action summary**
2. Summary is sent to the approver (admin or the user themselves)
3. Agent waits for explicit `"confirm"` or `"cancel"` input
4. Only then does the tool execute

### 4.4 Contextual Memory

The agent maintains a session dictionary keyed to `session_id`. Within a session:

- If the user says *"I can't log in"* and later adds *"Actually, it's for Slack"* — the agent merges the context.
- Session TTL: 30 minutes of inactivity (configurable).
- Session state is never shared across users.

### 4.5 Multi-Intent Detection

When a message contains more than one intent (e.g., *"My laptop is broken and I can't log in"*):

**Option A — Queue approach:** Identify both intents, address the higher-priority one first, then ask *"Also, did you want me to look into the login issue?"*

**Option B — Priority approach:** Define a priority order: `security > hardware > software > leave > policy`. The agent handles the highest-priority intent and surfaces the others.

Decide on one approach before building — retrofitting is painful.

---

## 5. Technical Stack

### The Brain (Intent Classifier)

#### Option A — Fine-tuned BERT (Production)
- Model: `DistilBERT` or `RoBERTa` via Hugging Face
- Latency: ~5–20ms per call
- Cost: ~$0 (runs locally)
- Training data needed: 50–200 examples per intent
- Adding new intent: requires retraining
- Best for: high-volume, privacy-sensitive deployments

#### Option B — LLM JSON Prompt (Prototyping) ← Start here
- Model: `GPT-4o-mini`, `Mistral`, or local `Llama 3`
- Latency: ~300–1500ms per call
- Cost: ~$0.0001–0.001 per call
- Training data needed: zero-shot capable
- Adding new intent: edit the prompt
- Best for: prototyping, rapidly-evolving intent definitions

**Recommended approach:** Start with the LLM prompt. Log every input/output pair. After 2–4 weeks of real traffic, fine-tune DistilBERT on the collected data. This is how most production teams build the fast classifier.

### The Orchestrator

| Framework | Why |
|---|---|
| **LangGraph** | State machine with loops and branches — ideal for clarification cycles |
| **PydanticAI** | Pythonic, enforces correct data types passed to tools |

### The Knowledge Base (RAG)

For the `policy_lookup` intent:

- **Vector DB:** ChromaDB (local) or Pinecone (cloud)
- **Embeddings:** `text-embedding-3-small` (OpenAI) or `all-MiniLM-L6-v2` (local)
- **Chunking strategy:** 512-token chunks with 50-token overlap
- **Citation requirement:** every RAG response must include the source document and chunk

### Tool Layer

```
Phase 3: Mock functions (print to console)
Phase 4: Real API calls, one by one
```

---

## 6. Architecture Overview

```
User Message
     │
     ▼
┌─────────────────────┐
│   Intent Classifier  │ ──── confidence < 0.40? ──→ Ask to rephrase
│  (LLM JSON / BERT)  │
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│   Confidence Check   │ ──── 0.40–0.79? ──→ Disambiguation question
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│   Slot Extractor    │ ──── missing slots? ──→ Clarification loop (max 2 turns)
│  + Context Memory   │
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│   Safety Guard      │ ──── dangerous action? ──→ HITL confirmation
│  (Identity, AuthZ)  │
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│    Tool Router      │
│  (Intent → Tool)    │
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│   Tool Executor     │ ──── tool error? ──→ Graceful failure message
│  (Mock → Real API)  │
└─────────────────────┘
     │
     ▼
  Response to User
```

---

## 7. Project Roadmap

### Phase 1 — The Contract (Week 1–2)
**Goal:** Define everything. Nothing runs yet.

- [ ] Write the intent–slot table (minimum 5 intents)
- [ ] Define Pydantic models for each intent's slots
- [ ] Write 10–15 example utterances per intent (include edge cases)
- [ ] Decide: what counts as a "dangerous" action? Document the list.
- [ ] Decide: multi-intent strategy (queue vs. priority)
- [ ] Set up project folder structure and Git repo

### Phase 2 — The Router (Week 2–3)
**Goal:** LLM classifies intent and extracts slots as validated JSON.

- [ ] Build LLM classifier with strict JSON output prompt
- [ ] Validate output against Pydantic schemas (reject malformed responses)
- [ ] Log every input + output pair to a JSONL file
- [ ] Test with 50 normal inputs
- [ ] Test with 50 adversarial inputs (ambiguous, multi-intent, malicious)
- [ ] Empirically determine confidence thresholds on the test set

### Phase 3 — Mock Tools + Slot Filling (Week 3–5)
**Goal:** Agent asks for missing slots and calls fake APIs.

- [ ] Build mock tool functions (print success/failure, don't call real APIs)
- [ ] Add slot-filling clarification loop (max 2 turns)
- [ ] Add session state management (`SessionStore` class)
- [ ] Add confidence-based disambiguation
- [ ] Add multi-intent detection
- [ ] End-to-end test: full conversation from greeting to mock tool call

### Phase 4 — Safety + RAG + Real APIs (Week 5–8)
**Goal:** Production-ready with real guardrails and real tools.

- [ ] Add identity guard (users cannot act on other users' accounts)
- [ ] Add HITL confirmation flow for dangerous actions
- [ ] Set up ChromaDB and ingest company policy PDFs
- [ ] Implement RAG pipeline for `policy_lookup` intent
- [ ] Add citation field to all RAG responses
- [ ] Swap mock functions → real API calls, one at a time
- [ ] Add error handling for each real API (timeouts, auth failures, etc.)
- [ ] Load and stress test the full pipeline

---

## 8. Risk Register

### Critical Risks

#### Identity Confusion
**Risk:** A user requests an action on another user's account (e.g., "reset John's password").  
**Impact:** Security breach, unauthorized access.  
**Mitigation:** Build the identity guard in Phase 1, not Phase 4. Every tool call must verify: `requesting_user == target_user OR requesting_user has admin role`.

#### Clarification Loop Hell
**Risk:** Agent asks 4–5 questions in a row, destroying the user experience.  
**Impact:** User abandonment, loss of trust.  
**Mitigation:** Hard cap of 2 clarification turns. Infer what you can. Escalate after cap is hit.

#### Multi-Intent Input
**Risk:** A single message contains 2+ valid intents. Classifier picks one at random.  
**Impact:** User's other request is silently dropped.  
**Mitigation:** Design the multi-intent strategy in Phase 1. Implement a priority queue or explicit intent list.

#### Uncalibrated Confidence Scores
**Risk:** LLM says "confidence: 0.85" for a genuinely uncertain classification.  
**Impact:** Agent proceeds with wrong intent. Tool executes incorrect action.  
**Mitigation:** Empirically calibrate thresholds on a labelled test set. Never trust raw confidence scores.

### Medium Risks

#### RAG Hallucination
**Risk:** Agent invents a policy that doesn't exist in the knowledge base.  
**Impact:** Employee acts on incorrect policy guidance.  
**Mitigation:** Every RAG response must cite the source document and chunk. No citation = no response.

#### Session State Corruption
**Risk:** Two concurrent requests for the same session_id cause a race condition.  
**Impact:** Garbled conversation state, wrong context applied.  
**Mitigation:** Use a proper session store (Redis or database) with locking, not a plain Python dict, in production.

#### Tool API Failures
**Risk:** Real API (Jira, HR portal, auth service) returns an error or times out.  
**Impact:** Agent fails silently or crashes.  
**Mitigation:** Every tool call must have explicit error handling with a user-friendly fallback message and a logged error.

---

## 9. Session & State Management

```python
import time
from typing import Optional
from pydantic import BaseModel

class SessionStore:
    def __init__(self, ttl_seconds: int = 1800):  # 30 min default
        self._sessions: dict[str, dict] = {}
        self._ttl = ttl_seconds

    def get(self, session_id: str) -> Optional[dict]:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if time.time() - session["last_active"] > self._ttl:
            self.expire(session_id)
            return None
        return session["data"]

    def update(self, session_id: str, data: dict) -> None:
        self._sessions[session_id] = {
            "data": data,
            "last_active": time.time()
        }

    def expire(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
```

### State fields per session

| Field | Type | Purpose |
|---|---|---|
| `session_id` | str | Unique identifier |
| `user_id` | str | Authenticated user — never trust from message content |
| `turn_count` | int | Total turns in conversation |
| `clarification_turns` | int | Turns spent asking for slots — capped at 2 |
| `pending_intent` | IntentResult | The last classified intent awaiting completion |
| `history` | list[dict] | Full conversation history for LLM context |

---

## 10. Logging Requirements

Log **every** input/output pair from day one. You cannot debug what you haven't logged. You cannot train BERT without labelled data.

### Log schema (JSONL — one object per line)

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

### What to log

- All inputs (even failed/ambiguous ones — these are the most valuable)
- All classified intents + confidence scores
- All slot extraction results (including missing slots)
- All tool calls + results + latency
- All clarification questions asked
- All HITL escalations

---

## 11. Safety & Security Requirements

### Identity & Authorization

```python
def check_authorization(
    requesting_user_id: str,
    target_user_id: str,
    action: str,
    user_roles: list[str]
) -> bool:
    # Users can always act on themselves
    if requesting_user_id == target_user_id:
        return True
    # Admins can act on others for password resets
    if action == "reset_password" and "it_admin" in user_roles:
        return True
    # All other cross-user actions require explicit admin role
    return "admin" in user_roles
```

### HITL Trigger Conditions

Define a `DANGEROUS_ACTIONS` list at configuration time:

```python
DANGEROUS_ACTIONS = {
    "reset_password": lambda slots, ctx: slots.get("username") != ctx.user_id,
    "software_request": lambda slots, ctx: slots.get("software_cost", 0) > 500,
    "hardware_issue": lambda slots, ctx: slots.get("severity") == "critical",
    "account_deletion": lambda slots, ctx: True,  # always HITL
}
```

### Input Sanitization

- Truncate all inputs to 2000 characters before passing to the LLM
- Strip HTML/script tags
- Log and reject inputs that match known prompt injection patterns
- Never pass raw user input directly as a system prompt

---

## 12. Intent Classifier Decision

### Recommended approach: LLM → BERT pipeline

**Step 1 (Weeks 1–5):** Use an LLM with a structured JSON prompt.

```
System prompt (abbreviated):
You are an IT support intent classifier. Given a user message, return ONLY valid JSON
matching this schema:
{
  "intent": one of ["reset_password", "check_leave", "software_request",
                    "policy_lookup", "hardware_issue", "unknown"],
  "confidence": float between 0.0 and 1.0,
  "slots": { extracted key-value pairs },
  "missing_slots": [ list of slot names that are missing ]
}

Do not add any text outside the JSON object.
```

**Step 2 (Weeks 5+):** Fine-tune DistilBERT on the logged data.
- Collect 200–500 examples per intent from real traffic
- Label using the LLM's classification (review manually)
- Fine-tune with Hugging Face `Trainer`
- A/B test the new classifier before switching over

---

## 13. Failure Mode Taxonomy

There are exactly four things that can go wrong. Each needs a distinct response path.

| Failure Mode | Condition | Agent Response |
|---|---|---|
| **Low confidence** | `confidence < 0.40` | *"I'm not sure I understood. Could you rephrase?"* |
| **Missing slots** | `len(missing_slots) > 0` | Ask for the missing slot (max 2 turns, then escalate) |
| **Dangerous action** | `is_dangerous == True` | Generate summary, trigger HITL, wait for confirmation |
| **Tool failure** | API returns error / timeout | *"I wasn't able to complete that. I've logged the issue — try again or contact IT directly."* |

---

## 14. First Day of Code

Do this in order. Don't skip to the chatbot interface.

### Step 1 — Project structure

```
it_support_agent/
├── models/
│   └── intent.py          # Pydantic schemas (IntentResult, SessionState)
├── classifier/
│   └── llm_classifier.py  # LLM JSON prompt + validation
├── tools/
│   ├── mock_tools.py      # Phase 3: mock implementations
│   └── real_tools.py      # Phase 4: real API calls
├── agent/
│   ├── session.py         # SessionStore
│   ├── slot_filler.py     # Clarification loop
│   └── safety.py          # Identity guard, HITL trigger
├── rag/
│   └── policy_search.py   # ChromaDB + RAG pipeline
├── logs/
│   └── events.jsonl       # Append-only log (gitignored)
├── tests/
│   ├── test_classifier.py
│   └── fixtures/
│       └── utterances.json  # 15 examples × 5 intents
└── main.py                # CLI entrypoint
```

### Step 2 — First script to run

```python
# main.py — Phase 1 proof of concept
from classifier.llm_classifier import classify_intent
from models.intent import IntentResult
import json

test_inputs = [
    "I need to reset my Slack password",
    "How many vacation days do I have left?",
    "My laptop screen is cracked",
    "Can I get Adobe Photoshop installed?",
    "What is the company's remote work policy?",
]

for text in test_inputs:
    result: IntentResult = classify_intent(text)
    print(f"Input:  {text}")
    print(f"Intent: {result.intent} ({result.confidence:.0%})")
    print(f"Slots:  {result.slots}")
    print(f"Missing: {result.missing_slots}")
    print("---")
```

### Step 3 — Write your 50 adversarial test cases

Before building anything else, write a `tests/fixtures/adversarial.json` with cases like:

- `"reset john.doe's email password"` → should trigger HITL
- `"I can't get into anything"` → should be low confidence
- `"My laptop broke and I need new software"` → multi-intent
- `"what's the policy on resetting passwords"` → `policy_lookup`, NOT `reset_password`
- `"I want to take some time off"` → missing `leave_type`

These will tell you immediately where your classifier breaks.

---

## Appendix: Example Utterances per Intent

### reset_password
- "I can't log into my email"
- "Reset my VPN password please"
- "I'm locked out of Slack"
- "My Office 365 password expired"
- "Can you reset my password for the HR portal?"

### check_leave
- "How many sick days do I have?"
- "What's my vacation balance?"
- "Can I check my leave entitlement?"
- "How much PTO do I have left this year?"
- "Am I entitled to more leave?"

### software_request
- "I need Figma installed on my laptop"
- "Can I get access to GitHub Copilot?"
- "Request Adobe Acrobat for my machine"
- "I need a licence for IntelliJ IDEA"
- "Can you get me Zoom Pro?"

### policy_lookup
- "What's the remote work policy?"
- "How many days notice for annual leave?"
- "What's the BYOD policy?"
- "What is the acceptable use policy for company devices?"
- "Is personal use of work laptop allowed?"

### hardware_issue
- "My monitor isn't working"
- "The keyboard on my MacBook is broken"
- "My docking station won't connect"
- "Laptop battery drains in 30 minutes"
- "My webcam isn't detected"

---

*Document version 1.0 — Generated May 2025*  
*Review and update the intent–slot table whenever a new tool or API is added.*