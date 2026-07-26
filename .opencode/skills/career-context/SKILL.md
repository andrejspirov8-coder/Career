---
name: career-context
description: Project overview and architecture for the Career job-search automation system
---

## Project structure

The Career repository is structured as a monorepo under `job-search/`:
- **Python backend** — uv-managed, Pydantic models, SQLite, Playwright, Ollama
- **Next.js dashboard** — `job-search/dashboard/`, Next.js 16.2.9 (Turbopack), React 19.2
- **Raycast extension** — `job-search/raycast-job-search-hub/`

## Key conventions

- `proxy.ts` is the Next.js 16 middleware filename (NOT `middleware.ts`)
- Python domain model files (`.models` / `_models`) must NOT import from `automation.*`, `dev_agents.*`, `integrations.*`, or `workspace.*`
- Cross-session memory lives in `job-search/.memory/` — read the index first
- Pre-commit hooks are installed — `make precommit-setup` to reinstall

## Key commands

| Task | Command |
|---|---|
| Python tests | `uv run --group dev python -m pytest -q` |
| Architecture test | `uv run pytest tests/test_architecture.py -q` |
| Lint | `uv run ruff check src mcp tools cv tests` |
| Dashboard typecheck | `cd dashboard && npm run typecheck` |
| Dashboard build | `cd dashboard && npm run build` |
| Log session note | `make remember TOPIC=<topic> MSG="<msg>"` |
| Session handoff | `make handoff GOAL="..." DONE="..." NEXT="..."` |
