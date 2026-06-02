# Contributing to `mid`

Thanks for your interest! `mid` is a small CLI that converts documents to Markdown
using Microsoft MarkItDown. Bug reports, documentation fixes, and small features are
especially welcome.

## Quick start

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]" "markitdown[all]"
```

## Run checks

```bash
python -m ruff check src tests
python -m pytest
```

## Rules

| Rule | Why |
|------|-----|
| Work inside `.venv` | Keeps dependencies isolated and matches CI |
| Validate real conversions, not just `--help` | A format only works when a real file round-trips |
| Keep temp files under `tmp/` or `temp/` | Repo root stays clean |
| Legacy `.doc` / `.xls` / `.ppt` → reject with a clear message | These formats need migration first |

## Commits and PRs

- Keep PRs focused on one concern.
- Update tests to cover the change.
- Run `ruff` and `pytest` locally before pushing.
- If CI fails, fix it — don't bypass it.
