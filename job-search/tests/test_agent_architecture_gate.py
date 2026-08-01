# tests/test_agent_architecture_gate.py
from __future__ import annotations

import secrets
import tempfile
from pathlib import Path

import pytest

from career_job_search.dev_agents.common import (
    CoordinatorError,
    CoordinatorPaths,
    load_settings,
)
from career_job_search.dev_agents.models import AgentTaskSpec
from career_job_search.dev_agents.snapshots import build_patch, create_snapshot


def _make_test_settings_and_paths(tmp_path: Path, repo_root: Path):
    """Create test settings and paths using the real config."""
    runtime = repo_root / "runtime" / "local-dev-agents"
    paths = CoordinatorPaths(
        repo_root=repo_root,
        git_root=repo_root,
        runtime_root=runtime,
        db_path=runtime / "agent_runs.sqlite3",
        worktree_root=tmp_path / "worktrees",
        backup_root=tmp_path / "backups",
    )
    settings = load_settings()
    return paths, settings


def _make_task_id() -> str:
    """Generate a valid task ID."""
    return f"agent_{secrets.token_hex(16)}"


def _setup_initial_repo(repo_root: Path):
    """Set up a minimal git repo with domain and infrastructure structure."""
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_root, check=True)

    # Add .gitignore to ignore runtime directory
    (repo_root / ".gitignore").write_text("runtime/\n.venv/\nnode_modules/\n*.pdf\n")

    # Create directory structure
    domain_dir = repo_root / "src/career_job_search/domain"
    infra_dir = repo_root / "src/career_job_search/infrastructure"
    domain_dir.mkdir(parents=True)
    infra_dir.mkdir(parents=True)

    # Create initial files
    infra_file = infra_dir / "database.py"
    infra_file.write_text("# Infrastructure module\n")

    domain_file = domain_dir / "matching.py"
    domain_file.write_text("# Domain module\n")

    # Commit initial state
    subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo_root, check=True)


def test_build_patch_rejects_architectural_violation():
    """Test that build_patch raises CoordinatorError on architectural violation in worktree."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Set up initial repo
        _setup_initial_repo(repo_root)

        paths, settings = _make_test_settings_and_paths(tmp_path, repo_root)

        task = AgentTaskSpec(
            objective="Test architectural violation",
            role="implementer",
            allowed_paths=["src/career_job_search/domain/matching.py"],
            acceptance_checks=[],
            risk="low",
            context_notes="",
            max_changed_files=1,
            max_diff_lines=10,
            timeout_seconds=60,
        )

        # Create snapshot (this copies repo to worktree)
        task_id = _make_task_id()
        snapshot = create_snapshot(task_id, settings=settings, paths=paths)

        # Modify the file IN THE WORKTREE to violate architecture
        worktree_domain_file = snapshot.worktree / "src/career_job_search/domain/matching.py"
        worktree_domain_file.write_text("from career_job_search.infrastructure.database import connect\n")

        # Try to build patch - should raise CoordinatorError due to architectural violation
        run_dir = paths.runtime_root / "runs" / task_id
        with pytest.raises(CoordinatorError) as exc_info:
            build_patch(task, snapshot, settings=settings, run_dir=run_dir)

        assert "Architectural violation" in str(exc_info.value)
        assert "domain" in str(exc_info.value)
        assert "infrastructure" in str(exc_info.value)


def test_build_patch_allows_valid_architecture():
    """Test that build_patch allows valid inward imports in worktree."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_root, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_root, check=True)

        # Add .gitignore to ignore runtime directory
        (repo_root / ".gitignore").write_text("runtime/\n.venv/\nnode_modules/\n*.pdf\n")

        # Create directory structure
        dev_agents_dir = repo_root / "src/career_job_search/dev_agents"
        core_dir = repo_root / "src/career_job_search/core"
        dev_agents_dir.mkdir(parents=True)
        core_dir.mkdir(parents=True)

        # Create initial files
        core_file = core_dir / "contracts.py"
        core_file.write_text("class Contract: pass\n")

        dev_agents_file = dev_agents_dir / "adapter.py"
        dev_agents_file.write_text("# Dev agents module\n")

        # Commit initial state
        subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo_root, check=True)

        paths, settings = _make_test_settings_and_paths(tmp_path, repo_root)

        task = AgentTaskSpec(
            objective="Test valid architecture",
            role="implementer",
            allowed_paths=["src/career_job_search/dev_agents/adapter.py"],
            acceptance_checks=[],
            risk="low",
            context_notes="",
            max_changed_files=1,
            max_diff_lines=10,
            timeout_seconds=60,
        )

        # Create snapshot
        task_id = _make_task_id()
        snapshot = create_snapshot(task_id, settings=settings, paths=paths)

        # Modify the file IN THE WORKTREE with valid inward import
        worktree_dev_agents_file = snapshot.worktree / "src/career_job_search/dev_agents/adapter.py"
        worktree_dev_agents_file.write_text(
            "from career_job_search.core.contracts import Contract\n"
        )

        # This should NOT raise an error
        run_dir = paths.runtime_root / "runs" / task_id
        patch_info = build_patch(task, snapshot, settings=settings, run_dir=run_dir)

        assert patch_info is not None
        assert "src/career_job_search/dev_agents/adapter.py" in patch_info.changed_files