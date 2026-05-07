# Classifier Design: LLM vs BERT

## Context

The classifier is the first decision point in the pipeline after domain guard:

```
User Input → Domain Guard → Query Rewrite → [CLASSIFIER] → Slot Validation → Safety Check → Tool
```

Its job is to produce an `IntentResult` — not just a label, but a structured object carrying `intent`, `confidence`, `slots`, and `missing_slots` in one shot.

---

## Current Approach: LLM Classifier

**Implementation:** `classifier/llm_classifier.py` → `classify_intent()`

The LLM receives a system prompt (`CLASSIFIER_SYSTEM_PROMPT`) and the (optionally rephrased) user message, and returns a single JSON object:

```json
{
  "intent": "reset_password",
  "confidence": 0.91,
  "slots": { "system_name": "Slack", "username": "bob" },
  "missing_slots": []
}
```

**What the LLM does in one pass:**
1. Classifies the intent across 5 categories
2. Extracts named slot values from free text
3. Identifies which required slots are absent
4. Assigns a calibrated confidence score

### Strengths

| Property | Detail |
|---|---|
| Zero training data | Works out of the box on our 5 intents |
| Slot extraction included | Classification and extraction happen in one API call |
| Handles ambiguity | Returns low confidence + `missing_slots` when uncertain |
| Prompt-tunable | Slot inference rules adjusted via `CLASSIFIER_SYSTEM_PROMPT` |
| Multi-intent aware | Returns structured data that `resolve_primary_intent()` can rank |

### Weaknesses

| Property | Detail |
|---|---|
| Latency | 300ms–2s per call depending on provider |
| Cost | Anthropic/OpenAI token cost per request |
| JSON fragility | LLM can hallucinate malformed output — mitigated by retry logic in `classify_intent()` |
| Non-deterministic | Same input can produce slightly different confidence values across calls |

---

## Alternative: BERT Intent Classifier

**Reference model:** [`Falconsai/intent_classification`](https://huggingface.co/Falconsai/intent_classification)

A fine-tuned BERT encoder that produces a softmax distribution over a fixed set of intent labels.

### Strengths

| Property | Detail |
|---|---|
| Speed | 10–50ms local inference vs 300ms–2s LLM |
| Cost | No API cost after model download (~400 MB) |
| Deterministic | Same input always produces the same output |
| Well-calibrated confidence | Softmax probability is reliable when fine-tuned on domain data |

### Weaknesses

| Property | Detail |
|---|---|
| No slot extraction | BERT outputs a label only — a separate NER or LLM call is needed for slots |
| Wrong intents out of the box | `Falconsai/intent_classification` is trained on generic intents (`GetWeather`, `PlayMusic`) — not `reset_password`, `check_leave`, etc. Fine-tuning on our 5 intents is required |
| Training data requirement | Fine-tuning needs ~500+ labelled examples per intent; the current fixture set (`tests/fixtures/utterances.json`) has ~25 total |
| Slot coupling | `IntentResult` carries slots alongside the intent — BERT cannot produce this contract without a second model |

---

## Side-by-Side Comparison

| Dimension | LLM (current) | BERT |
|---|---|---|
| Output contract | `intent + slots + confidence` in one call | `intent + confidence` only |
| Slot extraction | Included | Requires separate NER or LLM call |
| Latency | 300ms–2s | 10–50ms |
| API cost | Yes (Anthropic / OpenAI) | None after download |
| Training data needed | None | ~500+ examples per intent |
| Handles unseen phrasing | Yes (zero-shot generalisation) | Only if seen during fine-tuning |
| Deterministic | No | Yes |
| Model size | Remote API | ~400 MB local |
| Ready for our 5 intents | Yes | After fine-tuning only |

---

## Why the LLM Wins for This Project (Phases 1–3)

The core reason is the **slot extraction coupling**. Every downstream step — safety check, clarification loop, tool execution — depends on `IntentResult.slots`. BERT produces a label; it cannot fill slots.

Switching to BERT would require:

1. BERT call → intent label
2. Second model call (NER or LLM) → slot values
3. Merge both outputs into `IntentResult`

That is strictly worse than the current single LLM call.

The LLM also handles the query rewrite step's output naturally. A rephrased sentence like "The user wants to reset their Slack password" is understood zero-shot — BERT would need this style of input represented in its training set.

---

## When BERT Becomes the Right Choice

| Condition | Threshold |
|---|---|
| Request volume | > 10,000 requests/day (API cost becomes significant) |
| Training data available | ≥ 500 labelled examples per intent |
| Latency SLA | < 100ms end-to-end |
| Slot extraction handled separately | Via dedicated NER model or rule extractor |

---

## Recommended Phase 4 Hybrid Architecture

If production load justifies it, a two-stage pipeline avoids the full LLM cost on every request:

```
User Input
    │
    ▼
Domain Guard (keyword, free)
    │
    ▼
BERT Router (10–50ms, local)
    │ confidence ≥ 0.85 AND slots inferable from rules?
    ├─ YES → Rule-based slot extractor → IntentResult  (no LLM call)
    └─ NO  → LLM Classifier (current path) → IntentResult
```

This routes simple, high-confidence requests (e.g. "how many sick days do I have") without an LLM call, while preserving full LLM capability for ambiguous or slot-heavy requests.

**Prerequisite:** Fine-tune BERT on production traffic logs once enough labelled data accumulates from the LLM path.
