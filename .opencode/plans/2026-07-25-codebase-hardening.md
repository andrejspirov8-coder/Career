# Codebase Hardening Implementation Plan

**Goal:** Fix critical gaps, consolidate duplication, harden CI/CD, and clean up project structure.

**Architecture:** Surgical changes to specific files — no architectural rewrites. Each task is independently testable.

**Git constraint:** Per AGENTS.md, git operations require explicit user approval. Task 3 has git index operations that need extra approval.

---

### Task 1: Add missing dependencies to `pyproject.toml`
- Modify: `job-search/pyproject.toml`
- Add `httpx>=0.28,<1`, `qdrant-client>=1.13,<2`, `limits` in alphabetical order
- Run `uv lock`
- Verify: `uv run --group dev python -m pytest -q`

### Task 2: Add `lint` script to dashboard `package.json`
- Modify: `job-search/dashboard/package.json`
- Add `"lint": "eslint ."` to scripts block

### Task 3: Git index fixes (requires explicit approval)
- `git rm --cached job-search/pipeline/mcp_discovery_batch.jsonl job-search/pipeline/mcp_discovery_batch2.jsonl`
- `git add job-search/dashboard/\(dashboard\)/api/`

### Task 4: Consolidate atomic write utilities
- Modify: `core/json_io.py`, `dev_agents/common.py`, `recruiters/run_state.py`, `opportunities/dashboard_actions.py`
- Add `write_text_atomic()` to `core/json_io.py`, refactor `write_json_atomic` to delegate
- `dev_agents/common.py` re-exports from `core/json_io.py`
- `run_state.py` imports from `core/json_io.py`
- Add `write_csv_atomic()` to `core/json_io.py`, `dashboard_actions.py` imports it
- Verify: full test suite

### Task 5: Consolidate LinkedIn URL canonicalization
- Modify: `recruiters/identity.py`
- Delegate `normalise_profile_url` and `canonical_linkedin_profile_url` to `linkedin/selectors.py:canonical_profile_url`
- Verify: `pytest -q -x -k recruiter`

### Task 6: Document missing env vars
- Modify: `job-search/.env.example`
- Add: `FIRECRAWL_API_KEY`, `JOB_SEARCH_BROWSE_CLI`, `JOB_SEARCH_CHROME_EXECUTABLE`, `JOB_SEARCH_NO_LLM`, `LINKEDIN_JOBS_PROFILE_DIR`, `RECRUITER_LLM_TRACE`, `RECRUITER_LLM_VERBOSE`

### Task 7: Fix `make format`
- Modify: `job-search/Makefile`
- Replace `uv run black ...` with `uv run ruff format ...`

### Task 8: Pin vitest in Raycast
- Modify: `raycast-job-search-hub/package.json`
- `"vitest": "^4.0.0"` → `"vitest": "4.0.0"`

### Task 9: Add pre-commit hooks
- Modify: `.pre-commit-config.yaml`
- Add: `detect-private-key`, `check-merge-conflict`, `check-executables-have-shebangs`, `check-shebang-scripts-are-executable`, `mixed-line-ending`

### Task 10: Root `.gitignore` hardening
- Modify: `.gitignore`
- Add: `job-search/state/`, `job-search/runtime/`, `job-search/reports/`, `job-search/*.sqlite`, `job-search/*.db`, `.superpowers/`

### Task 11: Clean up Playwright CLI logs
- `rm -rf /Users/andrejspirov/Career/.playwright-cli/`

### Task 12: Clean up summary reports
- `mv job-search/summary_report_*.md job-search/reports/archive/`

### Task 13: CI hardening
- Modify: `.github/workflows/ci.yml`
- Add `pip-audit` step to python-test job
- Add `enable-cache: true` to `setup-uv` steps
- Verify `codeql-python` job exists

### Task 14: Remove unused prettier
- Modify: `raycast-job-search-hub/package.json`
- Remove `"prettier": "3.8.3"` line

### Task 15: Remove deprecated stub
- `git rm job-search/tools/recruiter_agent_orchestrate.py`
