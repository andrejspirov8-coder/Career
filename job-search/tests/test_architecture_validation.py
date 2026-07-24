# tests/test_architecture_validation.py
from __future__ import annotations

import importlib.util
import tempfile
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


def test_validate_architectural_boundaries_detects_violation():
    from career_job_search.dev_agents.architecture import (
        validate_architectural_boundaries,
    )

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
    from career_job_search.dev_agents.architecture import (
        validate_architectural_boundaries,
    )

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