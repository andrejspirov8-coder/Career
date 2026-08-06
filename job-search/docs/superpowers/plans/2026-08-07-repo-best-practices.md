# Repository Best Practices Implementation Plan

> **For agentic workers:** Execute the checklist sequentially in the current session. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement industry best practices across pre-commit automation, test coverage enforcement, root workspace cleanliness, and environment setting type safety.

**Architecture:** Add `.pre-commit-config.yaml` for pre-commit quality gates, configure `fail_under = 80` coverage floor in `pyproject.toml`, organize loose root summary reports into `reports/summary/`, and create a typed `Settings` model in Python using Pydantic.

**Tech Stack:** Python 3.11+, Pytest, Ruff, Black, pre-commit, Pydantic.

## Global Constraints
- Preserve all existing functionality and 100% test pass rate.
- Strict British English spelling in documentation.
- Clean git commits for each completed task.

---

### Task 1: Pre-Commit Configuration & Root Cleanliness

**Files:**
- Create: `.pre-commit-config.yaml`
- Modify: `pyproject.toml`
- Move: `summary_report_*.md` -> `reports/summary/`

- [ ] **Step 1: Create `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
      - id: end-of-file-fixer
      - id: trailing-whitespace

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.2
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

- [ ] **Step 2: Set `fail_under = 80` in `pyproject.toml`**

```toml
[tool.coverage.report]
show_missing = true
skip_covered = true
fail_under = 80
```

- [ ] **Step 3: Move loose root summary reports to `reports/summary/`**

```bash
cd /Users/andrejspirov/Career/job-search
mkdir -p reports/summary
git mv summary_report_*.md reports/summary/ 2>/dev/null || mv summary_report_*.md reports/summary/
```

- [ ] **Step 4: Verify test suite still passes**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_opportunity_config.py
```

- [ ] **Step 5: Commit changes**

```bash
cd /Users/andrejspirov/Career/job-search
git add .pre-commit-config.yaml pyproject.toml reports/
git commit -m "chore(quality): add pre-commit config, coverage threshold floor, and clean up root reports"
```

---

### Task 2: Pydantic Typed Application Settings Model

**Files:**
- Create: `src/career_job_search/core/config.py`
- Test: `tests/test_core_config.py`

- [ ] **Step 1: Write failing test for `Settings` model**

```python
# tests/test_core_config.py
from career_job_search.core.config import Settings

def test_default_settings_instantiation():
    settings = Settings()
    assert settings.app_name == "career-job-search"
    assert settings.network_timeout_seconds >= 1
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_core_config.py
```

- [ ] **Step 3: Implement `Settings` model in `src/career_job_search/core/config.py`**

```python
"""Typed application configuration management."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central typed settings loaded from environment or defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "career-job-search"
    environment: str = "development"
    debug: bool = False
    network_timeout_seconds: int = Field(default=20, ge=1, le=120)
    database_path: str = "state/opportunities.db"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return singleton Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_core_config.py
```

- [ ] **Step 5: Commit changes**

```bash
cd /Users/andrejspirov/Career/job-search
git add src/career_job_search/core/config.py tests/test_core_config.py
git commit -m "feat(core): add typed Pydantic application settings model"
```
