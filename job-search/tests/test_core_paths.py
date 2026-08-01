from __future__ import annotations

from pathlib import Path

from career_job_search.core.paths import (
    PROJECT_ROOT,
    project_path,
    resolve_project_root,
)


def test_resolve_project_root_returns_path():
    root = resolve_project_root()
    assert isinstance(root, Path)
    assert root.exists()


def test_resolve_project_root_uses_env_var(monkeypatch):
    monkeypatch.setenv("CAREER_JOB_SEARCH_ROOT", "/tmp/custom-root")
    root = resolve_project_root()
    assert str(root).endswith("/tmp/custom-root") or root == Path("/tmp/custom-root")


def test_resolve_project_root_uses_provided_env(monkeypatch):
    mock_env = {"CAREER_JOB_SEARCH_ROOT": "/env/override"}
    root = resolve_project_root(env=mock_env)
    assert root == Path("/env/override")


def test_resolve_project_root_returns_job_search_dir_when_env_not_set(monkeypatch):
    monkeypatch.delenv("CAREER_JOB_SEARCH_ROOT", raising=False)
    root = resolve_project_root()
    assert root.name.endswith("job-search") or str(root).endswith("job-search")


def test_project_root_is_path():
    assert isinstance(PROJECT_ROOT, Path)
    assert PROJECT_ROOT.exists()


def test_project_path_joins_under_project_root():
    parts = ("tools", "some_script.py")
    result = project_path(*parts)
    assert result == PROJECT_ROOT / "tools" / "some_script.py"


def test_project_path_single_part():
    result = project_path("README.md")
    assert result == PROJECT_ROOT / "README.md"


def test_project_path_empty():
    result = project_path()
    assert result == PROJECT_ROOT
