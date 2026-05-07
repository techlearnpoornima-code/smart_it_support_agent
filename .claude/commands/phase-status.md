# Check Phase 1 Status

Check the current build status of all Phase 1 deliverables.

1. List files under `models/`, `agent/`, `logs/`, `tests/fixtures/` — report which exist vs missing
2. Run `uv run pytest --tb=short -q` and report pass/fail counts
3. Run `uv run ruff check . --statistics` and report issues
4. Print a ✅/❌ checklist matching every item in docs/phase1.md

Be concise — one-line status per item.
