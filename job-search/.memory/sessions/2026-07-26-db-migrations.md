# 2026-07-26 — DB migration standardization + ruff cleanup

## What was done

### DB migration standardization (4 databases → use shared migrate_schema())
- `automation/queue.py`: Added `SCHEMA_VERSION=1`, `schema_meta` table in SCHEMA_SQL, switched from raw `executescript` to `migrate_schema()`
- `notifications/center.py`: Same pattern — `SCHEMA_VERSION=1`, `schema_meta`, `migrate_schema()`
- `recruiters/web_cache.py`: Extracted inline schema to `SCHEMA_SQL` constant, added `SCHEMA_VERSION=1`, `schema_meta` table, replaced `_connect()` with `connect_sqlite()` + `migrate_schema()`
- `recruiters/repository.py`: Already had `SCHEMA_VERSION` and `schema_meta`, but used raw `executescript` + manual version insert. Switched to `migrate_schema()`. Removed duplicate `PRAGMA foreign_keys`.

### Ruff cleanup (52→38, all remaining are intentional E402)
- UP035: `typing.Callable` → `collections.abc.Callable`
- S110: added noqa to 2 try-except-pass blocks
- S603/S607: file-level noqa for `generate-contracts.py`, per-line noqa for `doctor.py` and `browser.py`
- I001: auto-fixed 3 import-sort issues

### Verification
- Python tests: ✅ all pass
- Architecture tests: ✅ 10/10
- Dashboard tests: ✅ 22/22 (76 tests)
- Raycast tests: ✅ 7/7 (29 tests)
- Ruff: 38 (all E402, intentional conditional imports)
- 5/5 databases now use shared `migrate_schema()` from `core/sqlite.py`

### E402 cleanup (38→0)
All 38 E402 issues were trivially fixable — project-internal imports placed after `logger = logging.getLogger(__name__)`. Moved them above the logger line in 6 files:
- `opportunities/sources.py`, `recruiters/hiring_ranking.py`, `recruiters/ollama_agents.py`, `recruiters/orchestrator.py`, `recruiters/profile_enrichment.py`, `recruiters/web_research.py`

### Migration tests
Created `tests/test_db_migrations.py` — 16 tests covering:
- Fresh DB init for all 6 databases
- Idempotent re-init (double call)
- Core migrate_schema unit tests (version tracking, no-downgrade)
- v0→v1 backward compatibility

### _ensure_column
Verified all 7 columns already in SCHEMA_SQL. Added intent comment. No code change needed.

### Final state
- Ruff: 0 issues (was 52)
- Python tests: all pass
- Architecture: 10/10
- Dashboard: 22/22
- Raycast: 7/7
- npm: 2+20 vulns (blocked upstream)
- DB migrations: all 6 databases use migrate_schema() + tested
