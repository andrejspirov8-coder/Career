# Career Job Search Stabilization and Hardening Next Steps Plan

> **For agentic workers:** Use subagent-driven-development when independent task dispatch is available; otherwise execute the checklist sequentially in the current session. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Commit the validated config baseline, modularise `sources.py` into dedicated source adapters under `src/career_job_search/opportunities/sources/`, finalize fail-closed dashboard cookie auth, and standardise monthly vs annual salary normalisation for matching precision.

**Architecture:** Lock in the newly established configuration validation boundary (`config_validation.py`), refactor `sources.py` into a package of lightweight source adapters (`sources/` package) with clean contracts, harden Next.js session cookie signing and FastAPI auth bridge with fail-closed behavior, and normalise gross monthly vs annual compensation before scoring in `matching.py`.

**Tech Stack:** Python 3.11+, Pydantic v2, PyYAML, FastAPI, Next.js 16.2 / React 19, TypeScript, Vitest, Pytest.

## Global Constraints

- Preserve all existing SQLite database schemas and local-first data contracts.
- Fail-closed security posture across native macOS environment.
- Strict British English spelling for documentation and comments.
- Do not modify pre-existing unrelated dirty worktree files (`.memory/`, `supabase/`, etc.).
- Ensure 100% passing tests before making any completion assertions.

---

### Task 1: Lock in & Commit Config Baseline

**Files:**
- Modify: `config/opportunities.example.yaml`
- Modify: `src/career_job_search/opportunities/config_validation.py`
- Modify: `src/career_job_search/opportunities/orchestrator.py`
- Test: `tests/test_opportunity_config.py`

**Interfaces:**
- Consumes: `canonicalise_opportunities_config`, `load_and_validate_config`
- Produces: Committed Git baseline for opportunity config validation

- [ ] **Step 1: Run focused config tests to verify current green state**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_opportunity_config.py
```

- [ ] **Step 2: Inspect git status for config target files**

```bash
cd /Users/andrejspirov/Career/job-search
git status --short config/opportunities.example.yaml src/career_job_search/opportunities/config_validation.py src/career_job_search/opportunities/orchestrator.py
```

- [ ] **Step 3: Commit the config validation baseline**

```bash
cd /Users/andrejspirov/Career/job-search
git add config/opportunities.example.yaml src/career_job_search/opportunities/config_validation.py src/career_job_search/opportunities/orchestrator.py
git commit -m "feat(opportunities): canonicalise config validation and enforce local-safe example defaults"
```

- [ ] **Step 4: Verify git status after commit**

```bash
cd /Users/andrejspirov/Career/job-search
git status --short config/opportunities.example.yaml src/career_job_search/opportunities/config_validation.py src/career_job_search/opportunities/orchestrator.py
```

---

### Task 2: Modularise `sources.py` into Adapter Submodules

**Files:**
- Create: `src/career_job_search/opportunities/sources/__init__.py`
- Create: `src/career_job_search/opportunities/sources/base.py`
- Modify: `src/career_job_search/opportunities/sources.py`
- Test: `tests/test_sources_helper.py`
- Test: `tests/test_opportunity_system.py`

**Interfaces:**
- Consumes: `OpportunitiesConfig`, `SourceDiscovery`, `SourceResult`, `DiscoveryBatch`
- Produces: Package `career_job_search.opportunities.sources` with clean modular adapter imports and backwards-compatible public functions

- [ ] **Step 1: Create failing test for `sources` package modular import**

```python
# Create tests/test_sources_modular.py
from career_job_search.opportunities.sources import (
    DiscoveryBatch,
    SourceDiscovery,
    SourceResult,
    discover_opportunities_with_results,
)

def test_sources_package_exports():
    assert DiscoveryBatch is not None
    assert SourceDiscovery is not None
    assert SourceResult is not None
    assert callable(discover_opportunities_with_results)
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_sources_modular.py
```

- [ ] **Step 3: Create `src/career_job_search/opportunities/sources/base.py`**

```python
"""Base data structures and helper utilities for opportunity source adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from career_job_search.opportunities.models import Opportunity

@dataclass
class SourceResult:
    source: str
    status: str
    snapshot_type: str
    item_count: int
    duration_ms: int
    complete: bool
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "snapshot_type": self.snapshot_type,
            "item_count": self.item_count,
            "duration_ms": self.duration_ms,
            "complete": self.complete,
            "error": self.error,
        }

@dataclass
class DiscoveryBatch:
    opportunities: list[Opportunity] = field(default_factory=list)
    source_results: list[SourceResult] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        return any(result.status == "failed" for result in self.source_results)

@dataclass
class SourceDiscovery:
    opportunities: list[Opportunity] = field(default_factory=list)
    complete: bool = True
    status: str | None = None
    note: str = ""
```

- [ ] **Step 4: Update `src/career_job_search/opportunities/sources.py` to re-export and re-use `base.py`**

```python
from career_job_search.opportunities.sources.base import (
    DiscoveryBatch,
    SourceDiscovery,
    SourceResult,
)
```

- [ ] **Step 5: Run tests to verify all tests pass**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_sources_modular.py tests/test_sources_helper.py tests/test_opportunity_system.py
```

- [ ] **Step 6: Commit modular sources refactor**

```bash
cd /Users/andrejspirov/Career/job-search
git add src/career_job_search/opportunities/sources/base.py src/career_job_search/opportunities/sources.py tests/test_sources_modular.py
git commit -m "refactor(opportunities): extract base data structures into sources package"
```

---

### Task 3: Complete Fail-Closed Dashboard Session Auth Hardening

**Files:**
- Modify: `dashboard/lib/server/auth.ts`
- Modify: `dashboard/lib/server/session.ts`
- Modify: `src/career_job_search/api/auth.py`
- Test: `dashboard/lib/server/session.test.ts`
- Test: `tests/test_api_auth.py`

**Interfaces:**
- Consumes: Next.js cookie session store, FastAPI bearer token validator
- Produces: Fail-closed signed session cookies rejecting missing/invalid signatures without fallback bypass

- [ ] **Step 1: Write failing session test for unsigned cookie rejection**

```typescript
// in dashboard/lib/server/session.test.ts
import { describe, expect, it } from 'vitest';
import { verifySessionCookie } from './session';

describe('verifySessionCookie', () => {
  it('should reject un-signed or plain text session cookies', async () => {
    const session = await verifySessionCookie('plain-text-cookie-without-sig');
    expect(session).toBeNull();
  });
});
```

- [ ] **Step 2: Run Vitest to verify test failure**

```bash
cd /Users/andrejspirov/Career/job-search/dashboard
npx vitest run lib/server/session.test.ts
```

- [ ] **Step 3: Implement fail-closed signature check in `session.ts`**

```typescript
import { createHmac } from 'crypto';

export async function verifySessionCookie(cookieValue: string | undefined): Promise<Session | null> {
  if (!cookieValue || !cookieValue.includes('.')) {
    return null; // Fail closed if no signature delimiter is present
  }
  const [data, signature] = cookieValue.split('.');
  const secret = process.env.SESSION_SECRET;
  if (!secret) {
    return null; // Fail closed if secret is missing
  }
  const expectedSig = createHmac('sha256', secret).update(data).digest('hex');
  if (signature !== expectedSig) {
    return null; // Reject tampered or forged signatures
  }
  try {
    return JSON.parse(Buffer.from(data, 'base64').toString('utf-8'));
  } catch {
    return null;
  }
}
```

- [ ] **Step 4: Run Vitest to verify tests pass**

```bash
cd /Users/andrejspirov/Career/job-search/dashboard
npx vitest run lib/server/session.test.ts
```

- [ ] **Step 5: Run Python API auth test suite**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_api_auth.py
```

- [ ] **Step 6: Commit session auth hardening**

```bash
cd /Users/andrejspirov/Career/job-search
git add dashboard/lib/server/session.ts dashboard/lib/server/session.test.ts src/career_job_search/api/auth.py tests/test_api_auth.py
git commit -m "fix(auth): enforce fail-closed session cookie signature verification"
```

---

### Task 4: Normalise Monthly vs Annual Salary Parsing for Matching Precision

**Files:**
- Modify: `src/career_job_search/opportunities/matching.py`
- Modify: `src/career_job_search/opportunities/normalization.py`
- Test: `tests/test_opportunities_matching.py`

**Interfaces:**
- Consumes: Raw `salary_text` (e.g. `"2500 - 3500 €/mėn."`, `"€40,000 - €50,000 / year"`)
- Produces: Standardised annual gross compensation bounds (`min_annual_eur`, `max_annual_eur`) for fair scoring

- [ ] **Step 1: Write failing test for monthly vs annual salary normalisation**

```python
# in tests/test_opportunities_matching.py
from career_job_search.opportunities.normalization import normalise_salary_range

def test_normalise_monthly_salary_to_annual():
    res = normalise_salary_range("2500 - 3500 €/mėn")
    assert res == (30000.0, 42000.0)

def test_normalise_annual_salary():
    res = normalise_salary_range("€40,000 - €50,000 / year")
    assert res == (40000.0, 50000.0)
```

- [ ] **Step 2: Run pytest to verify test failure**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_opportunities_matching.py::test_normalise_monthly_salary_to_annual
```

- [ ] **Step 3: Implement `normalise_salary_range` in `normalization.py`**

```python
import re

def normalise_salary_range(text: str | None) -> tuple[float | None, float | None]:
    if not text:
        return (None, None)

    clean = text.lower().replace(",", "").replace(" ", "")
    # Check if monthly indicator exists
    is_monthly = any(kw in clean for k/kw in ("mėn", "men", "month", "mo"))

    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", clean)]
    if not numbers:
        return (None, None)

    if len(numbers) == 1:
        low = high = numbers[0]
    else:
        low, high = numbers[0], numbers[1]

    multiplier = 12.0 if is_monthly else 1.0
    return (low * multiplier, high * multiplier)
```

- [ ] **Step 4: Integrate `normalise_salary_range` into `match_opportunities` in `matching.py`**

```python
from career_job_search.opportunities.normalization import normalise_salary_range

# Use normalised annual salary bounds when calculating fit_score
min_sal, max_sal = normalise_salary_range(opportunity.salary_text)
```

- [ ] **Step 5: Run pytest to verify all matching tests pass**

```bash
cd /Users/andrejspirov/Career/job-search
uv run --group dev python -m pytest -v tests/test_opportunities_matching.py
```

- [ ] **Step 6: Commit salary normalisation**

```bash
cd /Users/andrejspirov/Career/job-search
git add src/career_job_search/opportunities/normalization.py src/career_job_search/opportunities/matching.py tests/test_opportunities_matching.py
git commit -m "feat(matching): normalise monthly vs annual salary text for consistent fit scoring"
```

---

### **Execution Choice**

Plan complete and saved to `docs/superpowers/plans/2026-08-07-career-job-search-next-steps.md`.

**Two execution options:**
1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session sequentially with verification checkpoints

Which approach would you like to proceed with?
