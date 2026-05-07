# Test Classifier

Test the intent classifier against a sample input (Phase 2+).

Usage: `/classify <user message>`

Steps:
1. If `classifier/llm_classifier.py` does not exist, report: "Classifier not built yet — complete Phase 2 first"
2. Otherwise run:
   `uv run python -c "from classifier.llm_classifier import classify_intent; import json; print(json.dumps(classify_intent('$ARGUMENTS').model_dump(), indent=2))"`
3. Display: intent, confidence, slots, missing_slots, is_dangerous
4. Flag LOW_CONFIDENCE if confidence < 0.40, flag DANGEROUS if is_dangerous is True
