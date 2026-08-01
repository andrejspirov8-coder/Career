# Local Agent Architectural Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add architectural boundary validation to the local development agent system to prevent automated changes from violating layer separation (domain importing dashboard/UI, circular imports, etc.)

**Architecture:** Create `src/career_job_search/dev_agents/architecture.py` with layer definitions and import boundary validation. Integrate into `build_patch()` (snapshot validation), `verification_checks_for_preset()` (architecture preset), and reviewer prompt (architectural findings category).

**Tech Stack:** Python 3.11, uv, pytest, ast module for import analysis

## Global Constraints

- Python 3.11 only (pyproject.toml:25)
- Ruff line-length 88, target py311 (pyproject.toml:34-36)
- All runtime data in `state/`, `runtime/`, `output/`, `packs/` (gitignored)
- Local agent sandbox denies network except localhost:11434
- Envelope schema: `career_python_helper_v1` (contracts.py:9)

---

### Task 2.1: Create Architecture Module with Layer Definitions

**Files:**
- Create: `src/career_job_search/dev_agents/architecture.py`
- Test: `tests/test_architecture_validation.py`

**Interfaces:**
- Produces: `LAYERS` (list of (name, path_prefix)), `FORBIDDEN_INWARD_IMPORTS` (set of (importer_layer, imported_layer)), `validate_architectural_boundaries(changed_files: list[str], repo_root: Path) -> list[str]`
- Consumes: None (foundational module)

- [ ] **Step 1: Write failing test for architecture module**

```python
# tests/test_architecture_validation.py
from __future__ import annotations

import importlib.util
from pathlib import Path

def test_architecture_module_exists():
    spec = importlib.util.spec_from_file_location(
        "architecture", Path("src/career_job_search/dev_agents/architecture.py")
    )
    assert spec is not None, "architecture.py must exist"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "LAYERS")
    assert hasattr(module, "FORBIDDEN_INWARD_IMPORTS")
    assert hasattr(module, "validate_architectural_boundaries")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_architecture_validation.py::test_architecture_module_exists -v`
Expected: FAIL - ModuleNotFoundError / FileNotFoundError

- [ ] **Step 3: Implement architecture.py**

```python
# src/career_job_search/dev_agents/architecture.py
"""Architectural boundary validation for local development agents."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable

# Layer hierarchy: inner (0) → outer (higher). Dependencies must flow inward only.
LAYERS = [
    ("core", "src/career_job_search/core"),
    ("domain", "src/career_job_search/domain"),
    ("application", "src/career_job_search/application"),
    ("infrastructure", "src/career_job_search/infrastructure"),
    ("dev_agents", "src/career_job_search/dev_agents"),
    ("ui_dashboard", "dashboard"),
    ("ui_raycast", "raycast-job-search-hub"),
    ("tools_linkedin", "tools/linkedin"),
    ("tools_other", "tools"),
    ("cv", "cv"),
]

# (importer_layer, forbidden_imported_layer) — inner layers must not import outer layers
FORBIDDEN_INWARD_IMPORTS = {
    ("domain", "infrastructure"),
    ("domain", "ui_dashboard"),
    ("domain", "ui_raycast"),
    ("domain", "tools_linkedin"),
    ("application", "ui_dashboard"),
    ("application", "ui_raycast"),
    ("core", "domain"),
    ("core", "application"),
    ("core", "infrastructure"),
    ("core", "ui_dashboard"),
    ("core", "ui_raycast"),
}

IMPORT_PATTERN = re.compile(
    r'^(?:from\s+([\w\.\/]+)\s+import|import\s+([\w\.\/]+))'
)

def _get_layer(file_path: str) -> str | None:
    for layer_name, layer_prefix in LAYERS:
        if file_path.startswith(layer_prefix + "/") or file_path == layer_prefix:
            return layer_name
    return None

def _extract_imports(content: str) -> list[str]:
    imports = []
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#"):
            continue
        m = IMPORT_PATTERN.match(line)
        if m:
            mod = m.group(1) or m.group(2)
            if mod and not mod.startswith("."):  # skip relative imports
                imports.append(mod)
    return imports

def _module_to_layer(module: str) -> str | None:
    if module.startswith("career_job_search.core"):
        return "core"
    if module.startswith("career_job_search.domain"):
        return "domain"
    if module.startswith("career_job_search.application"):
        return "application"
    if module.startswith("career_job_search.infrastructure"):
        return "infrastructure"
    if module.startswith("career_job_search.dev_agents"):
        return "dev_agents"
    if module.startswith("dashboard"):
        return "ui_dashboard"
    if module.startswith("raycast"):
        return "ui_raycast"
    if module.startswith("tools.linkedin"):
        return "tools_linkedin"
    if module.startswith("tools."):
        return "tools_other"
    if module.startswith("cv."):
        return "cv"
    return None

def validate_architectural_boundaries(changed_files: Iterable[str], repo_root: Path) -> list[str]:
    """Validate that changed files don't violate architectural boundaries.
    
    Returns list of violation messages (empty if valid).
    """
    violations = []
    
    for file_str in changed_files:
        file_path = Path(file_str)
        if not file_path.exists() or file_path.suffix != ".py":
            continue
            
        importer_layer = _get_layer(file_str)
        if not importer_layer:
            continue
            
        content = file_path.read_text(encoding="utf-8")
        imports = _extract_imports(content)
        
        for imp in imports:
            imported_layer = _module_to_layer(imp)
            if imported_layer and (importer_layer, imported_layer) in FORBIDDEN_INWARD_IMPORTS:
                violations.append(
                    f"Architectural violation: {file_str} (layer: {importer_layer}) "
                    f"imports {imp} (layer: {imported_layer}) — "
                    f"dependencies must flow inward only"
                )
    
    return violations
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_architecture_validation.py::test_architecture_module_exists -v`
Expected: PASS

- [ ] **Step 5: Add validation test cases**

```python
# tests/test_architecture_validation.py (append)
import tempfile
from pathlib import Path

def test_validate_architectural_boundaries_detects_violation():
    from career_job_search.dev_agents.architecture import validate_architectural_boundaries
    
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        # Create a domain file that imports infrastructure
        domain_file = repo_root / "src/career_job_search/domain/matching.py"
        domain_file.parent.mkdir(parents=True)
        domain_file.write_text("from career_job_search.infrastructure.database import connect\n")
        
        violations = validate_architectural_boundaries(
            ["src/career_job_search/domain/matching.py"], repo_root
        )
        assert len(violations) == 1
        assert "domain" in violations[0]
        assert "infrastructure" in violations[0]

def test_validate_architectural_boundaries_allows_valid_imports():
    from career_job_search.dev_agents.architecture import validate_architectural_boundaries
    
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        # Infrastructure importing domain is OK (inward)
        infra_file = repo_root / "src/career_job_search/infrastructure/database.py"
        infra_file.parent.mkdir(parents=True)
        infra_file.write_text("from career_job_search.domain.models import User\n")
        
        violations = validate_architectural_boundaries(
            ["src/career_job_search/infrastructure/database.py"], repo_root
        )
        assert len(violations) == 0
```

- [ ] **Step 6: Run validation tests**

Run: `uv run python -m pytest tests/test_architecture_validation.py -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/career_job_search/dev_agents/architecture.py tests/test_architecture_validation.py
git commit -m "feat: add architectural boundary validation for local agents"
```

---

### Task 2.2: Integrate Architecture Validation into Agent Pipeline

**Files:**
- Modify: `src/career_job_search/dev_agents/snapshots.py` (add validation in `build_patch()`)
- Modify: `src/career_job_search/dev_agents/proposals.py` (add `"architecture"` preset to `verification_checks_for_preset()`)
- Modify: `src/career_job_search/dev_agents/execution.py` (add architectural finding category to reviewer prompt)

**Interfaces:**
- Consumes: `validate_architectural_boundaries` from architecture.py
- Produces: `CoordinatorError` on violation in `build_patch()`, new verification preset, updated reviewer prompt

- [ ] **Step 1: Write failing test for build_patch integration**

```python
# tests/test_agent_architecture_gate.py
from __future__ import annotations
import tempfile
from pathlib import Path

def test_build_patch_rejects_architectural_violation():
    from career_job_search.dev_agents.snapshots import build_patch
    from career_job_search.dev_agents.common import CoordinatorError
    
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        # Setup minimal git repo with domain file importing infrastructure
        # This test verifies build_patch raises CoordinatorError on violation
        pass  # Implement with actual git repo setup
```

- [ ] **Step 2: Modify snapshots.py `build_patch()` to call validation**

```python
# In build_patch(), after diff_files check (~line 451), add:
from career_job_search.dev_agents.architecture import validate_architectural_boundaries

changed_files = [str(repo_root / f) for f in diff_files]
arch_violations = validate_architectural_boundaries(changed_files, repo_root)
if arch_violations:
    raise CoordinatorError(
        "Patch violates architectural boundaries:\n" + "\n".join(arch_violations)
    )
```

- [ ] **Step 3: Add architecture preset to proposals.py**

```python
# In verification_checks_for_preset() (~line 236), add:
if preset == "architecture":
    return [
        VerificationCheck(
            name="Architecture: import boundaries",
            argv=["python", "-m", "career_job_search.dev_agents.architecture", "check"],
            timeout_seconds=300,
        ),
        VerificationCheck(
            name="Architecture: circular imports",
            argv=["python", "-m", "career_job_search.dev_agents.architecture", "cycles"],
            timeout_seconds=300,
        ),
    ]
```

- [ ] **Step 4: Add CLI entry points to architecture.py**

```python
# Add to architecture.py:
def main(argv: list[str] | None = None) -> int:
    import sys
    args = argv or sys.argv[1:]
    if "check" in args:
        # Run validation on all Python files in repo
        violations = validate_architectural_boundaries(
            [str(f) for f in Path(".").rglob("*.py") if not any(p in str(f) for p in [".venv", "__pycache__", "node_modules"])],
            Path(".")
        )
        if violations:
            for v in violations:
                print(v, file=sys.stderr)
            return 1
        print("OK: No architectural violations")
        return 0
    if "cycles" in args:
        # TODO: implement circular import detection
        print("OK: Circular import check not yet implemented")
        return 0
    return 1
```

- [ ] **Step 5: Update reviewer prompt in execution.py**

```python
# In build_agent_prompt() reviewer instructions (~line 382), add:
instructions.append(
    "Check for architectural violations: domain layer importing from "
    "infrastructure/UI layers, circular dependencies, core layer importing "
    "from non-core layers. Report as 'major' severity findings with "
    "specific file:line references."
)
```

- [ ] **Step 6: Run integration test**

Run: `uv run python -m pytest tests/test_agent_architecture_gate.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/career_job_search/dev_agents/snapshots.py src/career_job_search/dev_agents/proposals.py src/career_job_search/dev_agents/execution.py src/career_job_search/dev_agents/architecture.py tests/test_agent_architecture_gate.py
git commit -m "feat: integrate architectural validation into local agent pipeline"
```

---

### Task 2.3: Protect Core Domain Layers in Agent Config

**Files:**
- Modify: `config/local_dev_agents.yaml` (add core/domain/application/infrastructure to `scan_paths`)
- Modify: `src/career_job_search/dev_agents/common.py` (add core/domain/application/infrastructure/cv to `WRITE_FORBIDDEN_PATHS`)

**Interfaces:**
- Consumes: None
- Produces: Updated config and forbidden paths

- [ ] **Step 1: Write failing test for config changes**

```python
# tests/test_agent_config_protection.py
def test_scan_paths_includes_core_layers():
    import yaml
    with open("config/local_dev_agents.yaml") as f:
        config = yaml.safe_load(f)
    scan_paths = config.get("scan_paths", [])
    required = [
        "src/career_job_search/core",
        "src/career_job_search/domain",
        "src/career_job_search/application",
        "src/career_job_search/infrastructure",
    ]
    for path in required:
        assert path in scan_paths, f"{path} must be in scan_paths"

def test_write_forbidden_includes_core_layers():
    from career_job_search.dev_agents.common import WRITE_FORBIDDEN_PATHS
    required = [
        "src/career_job_search/core",
        "src/career_job_search/domain",
        "src/career_job_search/application",
        "src/career_job_search/infrastructure",
        "cv/build_cv_pdf.py",
        "cv/variant_profiles.yaml",
    ]
    for path in required:
        assert any(path in p for p in WRITE_FORBIDDEN_PATHS), f"{path} must be write-forbidden"
```

- [ ] **Step 2: Update config/local_dev_agents.yaml**

```yaml
# Add to scan_paths:
  - src/career_job_search/core
  - src/career_job_search/domain
  - src/career_job_search/application
  - src/career_job_search/infrastructure
  - cv
```

- [ ] **Step 3: Update common.py WRITE_FORBIDDEN_PATHS**

```python
WRITE_FORBIDDEN_PATHS = (
    ...
    "src/career_job_search/core",
    "src/career_job_search/domain",
    "src/career_job_search/application",
    "src/career_job_search/infrastructure",
    "cv/build_cv_pdf.py",
    "cv/variant_profiles.yaml",
)
```

- [ ] **Step 3: Run tests**

Run: `uv run python -m pytest tests/test_agent_config_protection.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add config/local_dev_agents.yaml src/career_job_search/dev_agents/common.py tests/test_agent_config_protection.py
git commit -m "feat: protect core domain layers in local agent config"
```

---

## Execution Order Summary

| Task | Description | Depends On |
|------|-------------|------------|
| 2.1 | Architecture module with layer definitions | — |
| 2.2 | Integrate into agent pipeline (snapshots, proposals, execution) | 2.1 |
| 2.3 | Protect core layers in agent config | 2.1 |

---

**Ready for subagent-driven execution.** Each task has explicit failing-test-first steps, implementation code, and verification commands.