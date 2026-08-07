# Repository Architecture & Hardening Implementation Plan

> **For agentic workers:** Execute the checklist sequentially in the current session. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a modular source adapter registry, SQLite WAL/busy timeout resilience, FastAPI OpenAPI export script, and CI pipeline hardening.

**Architecture:** Refactor opportunity sources into a clean plugin registry (`sources/registry.py`), add SQLite PRAGMAs (`WAL` and `busy_timeout`) in repository connection managers, write an OpenAPI schema generator script for frontend type sync, and update `.github/workflows/ci.yml` with `uv lock --check` and `pre-commit` verification.

**Tech Stack:** Python 3.11+, SQLite, FastAPI, Next.js, Pytest, GitHub Actions.

## Global Constraints
- Retain 100% passing tests across all components.
- Strict British English spelling in documentation and comments.
- Clean git commit for each task.

---

### Task 1: SQLite WAL Mode & Busy Timeout Hardening

**Files:**
- Modify: `src/career_job_search/opportunities/repository.py`
- Test: `tests/test_persistence_policy.py`

- [ ] **Step 1: Write test for SQLite PRAGMAs**

```python
# in tests/test_persistence_policy.py
from career_job_search.opportunities.repository import get_db_connection

def test_sqlite_pragmas_enabled():
    conn = get_db_connection(":memory:")
    cur = conn.cursor()
    timeout = cur.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout >= 5000
    conn.close()
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_persistence_policy.py
```

- [ ] **Step 3: Update `get_db_connection` in `repository.py`**

```python
def get_db_connection(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000;")
    if str(db_path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")
    return conn
```

- [ ] **Step 4: Run test to verify pass**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_persistence_policy.py
```

- [ ] **Step 5: Commit SQLite hardening**

```bash
cd /Users/andrejspirov/Career/job-search
git add src/career_job_search/opportunities/repository.py tests/test_persistence_policy.py
git commit -m "fix(db): enable SQLite WAL mode and 5000ms busy timeout"
```

---

### Task 2: FastAPI OpenAPI Schema Export Script

**Files:**
- Create: `src/career_job_search/api/openapi.py`
- Modify: `Makefile`
- Test: `tests/test_api_server.py`

- [ ] **Step 1: Write test for OpenAPI export script**

```python
# in tests/test_api_server.py
from career_job_search.api.openapi import generate_openapi_schema

def test_openapi_schema_generation():
    schema = generate_openapi_schema()
    assert isinstance(schema, dict)
    assert "openapi" in schema
    assert "paths" in schema
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_api_server.py::test_openapi_schema_generation
```

- [ ] **Step 3: Implement `generate_openapi_schema` in `src/career_job_search/api/openapi.py`**

```python
"""OpenAPI schema generation utility for frontend type sync."""

from __future__ import annotations

import json
from typing import Any
from career_job_search.api.server import app

def generate_openapi_schema() -> dict[str, Any]:
    return app.openapi()

def main() -> None:
    schema = generate_openapi_schema()
    print(json.dumps(schema, indent=2))

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add `generate-types` recipe to `Makefile`**

```makefile
generate-types:
	$(PY) -m career_job_search.api.openapi > dashboard/lib/api/openapi.json
```

- [ ] **Step 5: Run test to verify pass**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_api_server.py
```

- [ ] **Step 6: Commit OpenAPI export utility**

```bash
cd /Users/andrejspirov/Career/job-search
git add src/career_job_search/api/openapi.py Makefile tests/test_api_server.py
git commit -m "feat(api): add OpenAPI schema exporter and generate-types Makefile target"
```

---

### Task 3: Modular Source Plugin Registry (`sources/registry.py`)

**Files:**
- Create: `src/career_job_search/opportunities/sources_package/registry.py`
- Test: `tests/test_sources_registry.py`

- [ ] **Step 1: Write test for Source Adapter Registry**

```python
# tests/test_sources_registry.py
from career_job_search.opportunities.sources_package.registry import (
    SourceRegistry,
    register_source,
    get_registered_sources,
)

def test_source_registry_registration():
    registry = SourceRegistry()
    registry.register("test_source", lambda cfg, **kw: None)
    assert "test_source" in registry.list_sources()
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_sources_registry.py
```

- [ ] **Step 3: Implement `SourceRegistry` in `sources_package/registry.py`**

```python
"""Registry for modular opportunity source adapters."""

from __future__ import annotations

from typing import Any, Callable

class SourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, fn: Callable[..., Any]) -> None:
        self._sources[name] = fn

    def list_sources(self) -> list[str]:
        return list(self._sources.keys())

    def get(self, name: str) -> Callable[..., Any] | None:
        return self._sources.get(name)

_DEFAULT_REGISTRY = SourceRegistry()

def register_source(name: str, fn: Callable[..., Any]) -> None:
    _DEFAULT_REGISTRY.register(name, fn)

def get_registered_sources() -> list[str]:
    return _DEFAULT_REGISTRY.list_sources()
```

- [ ] **Step 4: Run test to verify pass**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_sources_registry.py
```

- [ ] **Step 5: Commit Source Registry**

```bash
cd /Users/andrejspirov/Career/job-search
git add src/career_job_search/opportunities/sources_package/registry.py tests/test_sources_registry.py
git commit -m "feat(opportunities): add modular source adapter registry"
```

---

### Task 4: CI Workflow Hardening

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Inspect current `.github/workflows/ci.yml`**

```bash
cat .github/workflows/ci.yml
```

- [ ] **Step 2: Add `uv lock --check` and `pre-commit` steps to `.github/workflows/ci.yml`**

Ensure workflow steps include:
- `uv lock --check`
- `uv run --group dev python -m pytest`

- [ ] **Step 3: Commit CI hardening workflow**

```bash
cd /Users/andrejspirov/Career/job-search
git add .github/workflows/ci.yml
git commit -m "ci: enforce uv lockfile verification and pre-commit checks"
```
