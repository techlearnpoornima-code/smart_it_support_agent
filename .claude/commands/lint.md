# Lint and Format

Run ruff linter and formatter on the codebase.

1. Run `uv run ruff check . --fix` to auto-fix safe issues
2. Run `uv run ruff format .` to format all files
3. Run `uv run ruff check .` again to confirm zero remaining issues
4. Report any issues that could not be auto-fixed with file:line references
