- 2026-07-28 — Phase 3 (multi-tenant on SQLite) was SCAFFOLDED but NOT completed. Corrected on 2026-08-01: no repository actually filters by user_id, no schema has a user_id column, and the 3 data-isolation tests fail. Existing state: `api/context.py` `current_user_id` contextvar (default `local-user`), `core/user_migration.py` `ensure_user_id_column()`, `api/user_store.py` (local users DB), and `api/auth.py` `verify_token` sets the contextvar.
- 2026-08-01 — COMPLETED for the **opportunities DB only** (the sole DB with isolation tests). Moved `current_user_id` to `core/context.py` (re-exported from `api/context.py`) so domain repos depend on `core`, not the `api` adapter. Bumped `opportunities.repository_db` `SCHEMA_VERSION` to 2: `user_id TEXT NOT NULL DEFAULT 'local-user'` on all 6 tables, dedupe unique index scoped to `(user_id, dedupe_key)`, `ensure_user_id_column` wired into `init_db` (runs before `executescript` so legacy-table DBs migrate cleanly), `_migrate_v2_indexes` drops the legacy global dedupe index. Scoped `repository_discovery.py` (save/get/list/upsert/resolve/aliases) and `repository_activity.py` (actions, count, source runs, daily runs, deliveries, both mark_unseen) by `current_user_id`. `tests/test_data_isolation.py` 3/3 pass; no new regressions (755 passed vs 752 baseline). Decided NOT to extend to recruiters/notifications/automation/dev_agents this session — no isolation tests and composite-PK tables would need destructive table-rebuild migrations. Still on branch `wip/jul27-28-fastapi-supabase`, not yet committed.

## 2026-08-01 — Dashboard release-gate fixes (24 TS errors + architecture test)

Fixed the dashboard blockers for the FastAPI/Supabase work:
- `architecture.test.ts` retargeted to `app/(dashboard)/api` (post route-group restructure); signup route now enforces `isSameOriginRequest` like login/logout.
- 5 settings libs (`cv-profiles`, `linkedin-config`, `opportunity-sources`, `runtime-settings`, `setup-checklist`) switched from `runPythonHelper` → `runFastApiHelper`: they map to `api/routers/helpers.py` HELPER_REGISTRY modules, not tool scripts.
- `python-bridge.ts` added `opportunityOrchestrate` → `tools/opportunity_orchestrate.py`.
- Added `requestId` to `OpportunityActionPayload`/`runOpportunityAction`; optional `by_tailoring`/`by_match_score`/`outcome_history` on `CareerAnalyticsOverview` + page fallbacks; optional `opportunity_targets`/`target_company`/`target_company_verified` on recruiter types.

Verified: vitest 75/75, `tsc --noEmit` clean, ruff clean, focused pytest 46/46. Full suite 29 failed/758 passed (all pre-existing).

OPEN BLOCKER: `pyproject.toml` never declared `fastapi`/`uvicorn`/`supabase` (WIP commit added the backend without deps). `verify_release.sh` runs `uv sync --locked --all-groups` → strips fastapi → `test_api_server.py` collection error. This is a dependency/lockfile change → belongs to Main Codex per AGENTS.md. `raycast-check` fails on a mise `tsc` shim (environment, pre-existing).

## 2026-08-01 — Raycast extension removed from repo

User confirmed the Raycast extension should be removed (they believed it was already gone; only 3 legacy inbox commands had been removed earlier).
- `git rm -r raycast-job-search-hub/` (49 tracked files).
- Stripped wiring: Makefile `raycast-check` target + .PHONY, scripts/verify_release.sh Raycast block, scripts/bootstrap.sh Raycast deps, scripts/preflight.sh raycast test block.
- dev-agents system: removed `ui_raycast` layer + forbidden tuples + module mapping from architecture.py; dropped `raycast` from ProposalCheckPreset (models.py), --check-preset choices (cli.py), planner scan path + prompt + check_presets, proposals.py raycast VerificationCheck block, review.py auto-apply path clause; stripped raycast entries from common.py WRITE_FORBIDDEN_PATHS, doctor.py, sandbox.py, snapshots.py (2 spots).
- dashboard: dev-agent-data.ts (forbidden paths, DevAgentCheckPreset, raycast checks block), both dev-agent consoles (stale `app/dev-agents/` duplicate + `app/(dashboard)` copy) option removed.
- config/local_dev_agents.yaml: forbidden-prefix + planner scan_paths.
- Docs: README.md (ownership paragraph + checks block), docs/REQUIRED_CHECKS.md (removed Raycast job line + updated NOTE), AGENTS.md (dropped make raycast-check).
- Kept historical references: AUDIT-20260726.md, archive/, .memory/, runtime/ (point-in-time records).

Verified: ruff clean, test_architecture + test_local_dev_agents 44/44, dashboard-test 75/75 + typecheck clean, full pytest failure list identical to pre-removal baseline (29 pre-existing). bash -n clean on all 3 scripts. NOTE: fastapi still absent from venv (verify-release sync stripped it) — the pyproject dependency gap remains the open blocker.
