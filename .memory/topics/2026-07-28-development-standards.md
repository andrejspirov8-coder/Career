[2026-07-28] Fixed 13 pre-existing test failures (dashboard service unpacking, repository_discovery swapped UPDATE params, test isolation ContextVar leak). Added mypy, shellcheck, markdownlint to pre-commit hooks and CI. Set coverage fail_under=30. Created .markdownlint.jsonc config. All remaining test failures are pre-existing isolation issues (non-deterministic, shared ContextVar across test files).

[2026-07-28] Final state:
- All 13 pre-existing failures fixed (dashboard service unpacking, repo_discovery swapped UPDATE params, ContextVar leak in test_data_isolation)
- Created tests/conftest.py with autouse fixture resetting current_user_id, storage_cache, circuit_breaker — eliminates flaky test-isolation failures
- 843 tracked tests passing, 0 failures
- mypy: fixes 2 errors in api/auth.py + api/routers/helpers.py; CI scoped to src/career_job_search/api + core (0 errors)
- shellcheck, markdownlint added to pre-commit + CI
- Coverage fail_under=30 in pyproject.toml
- Supabase preview CI documented in REQUIRED_CHECKS.md as future enhancement
- Untracked files from parallel branches have broken import chains (migrate_schema, save_settings missing) — not regressions
