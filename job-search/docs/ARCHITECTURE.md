# Repository architecture

This private repository is the only active source of truth for the Career
workspace. Adjacent Career folders are historical copies and must never be
used as automation write targets.

## Ownership and dependency direction

The Python implementation lives under `src/career_job_search/` and is grouped
by capability: shared core utilities, CVs, opportunities, recruiters,
automation, notifications, workspace controls, development agents, and the
LinkedIn integration. Dependencies flow in one direction:

```text
domain models -> services -> repositories/integrations -> CLI and web adapters
```

Domain code may not import dashboard or CLI modules. Integrations may depend on
domain protocols, but domain modules may not depend on concrete browser or UI
implementations. `tools/*.py` and `cv/build_cv_pdf.py` remain stable command
wrappers so existing Make, dashboard, Raycast, and operator commands continue
to work while implementation moves into the package.

The dashboard owns presentation and user interaction. Scoring, eligibility,
risk rules, status transitions, and live-dispatch policy remain in Python. All
dashboard-to-Python calls use the shared server bridge and versioned JSON
contracts. Raycast uses the same Python commands and never reimplements domain
rules.

## Sources of truth

- Python dependencies: `pyproject.toml` and `uv.lock`.
- CV catalogue and matching metadata: `cv/variant_profiles.yaml`.
- Editable CV content: Markdown files under `cv/`.
- Recruiter runtime policy: validated configuration under `linkedin/` with the
  hard live-send ceiling enforced in Python.
- Opportunity discovery defaults: `config/opportunities.example.yaml`, merged
  with private preferences stored under ignored `state/`.
- Operational commands: the root `Makefile` and `docs/OPERATIONS_RUNBOOK.md`.

## Runtime data

Runtime and private data stay outside Git. This includes `.env*`, `state/`,
`runtime/`, browser profiles, generated PDFs, application packs, pipeline
records, logs, caches, and test/build output. Each capability owns its existing
SQLite database; the architecture does not merge databases or migrate data.
See [`docs/SCHEMAS.md`](SCHEMAS.md) for the schema of every SQLite database
and persisted store under `state/`.

## Entry points

- Dashboard: `make dashboard-dev` or `make dashboard-start`.
- Safe daily search: `make daily-queue`.
- CV generation: `make rebuild-cvs`.
- Recruiter review: `career_job_search.recruiters.orchestrator` through `uv run python`.
- Complete verification: `make verify-release`.

## Historical material

Files under `archive/` are preserved evidence only. They are excluded from
runtime imports, dependency setup, lint targets, CI decisions, and work
proposals. Current instructions always take precedence over archived
content.


## Dashboard route groups

The Next.js dashboard uses a route-group pattern to scope authentication. The
`app/(dashboard)/` route group wraps all authenticated pages behind a shared
layout (`app/(dashboard)/layout.tsx`) that checks the dashboard token and
redirects unauthenticated requests to `app/login/`. Routes outside the
`(dashboard)` group — currently only the login page — are unauthenticated by
default. This keeps auth logic in one layout instead of per-page middleware.

## Persistence and time

Application CSV and outcome JSONL writers share an advisory `fcntl.flock` lock. CSV replacements are temporary-file + flush + fsync + `os.replace`; JSONL records are complete fsynced lines. Local application, response, reminder, and analytics dates use `Europe/Vilnius`; UTC timestamps remain suitable for audit instants.

### Remote persistence is dormant

Local SQLite under `state/` is the only supported runtime persistence layer.
The `supabase/` directory contains unapplied historical migration material and
is not an active fallback, deployment path, or runtime dependency. Its helper is
intentionally fail-closed. A remote persistence implementation would require a
separate reviewed architecture, security, migration, rollback, and credential
plan with explicit owner approval.
