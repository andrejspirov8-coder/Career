"""Architecture invariants for the canonical Career repository."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from career_job_search.cvs.catalogue import load_cv_catalogue

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "career_job_search"
TOOLS_ROOT = ROOT / "tools"
MAX_PRODUCTION_MODULE_LINES = 800
MAX_TOOL_WRAPPER_LINES = 25


def _module_name(path: Path) -> str:
    if path.is_relative_to(PACKAGE_ROOT):
        parts = list(path.relative_to(ROOT / "src").with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)
    return path.stem


def _active_modules() -> dict[str, Path]:
    paths = [*PACKAGE_ROOT.rglob("*.py"), *TOOLS_ROOT.glob("*.py")]
    return {_module_name(path): path for path in paths}


def _import_targets(path: Path, module: str, known: set[str]) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: set[str] = set()
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    for node in ast.walk(tree):
        candidates: list[str] = []
        if isinstance(node, ast.Import):
            candidates.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package_parts = package.split(".") if package else []
                keep = max(0, len(package_parts) - (node.level - 1))
                prefix = package_parts[:keep]
                base = ".".join([*prefix, *(node.module or "").split(".")]).strip(".")
            else:
                base = node.module or ""
            candidates.append(base)
            candidates.extend(
                f"{base}.{alias.name}" for alias in node.names if base and alias.name != "*"
            )
        for candidate in candidates:
            if candidate in known:
                targets.add(candidate)
    return targets


def _cycle(graph: dict[str, set[str]]) -> list[str]:
    visited: set[str] = set()
    active: list[str] = []
    active_set: set[str] = set()

    def visit(module: str) -> list[str]:
        if module in active_set:
            start = active.index(module)
            return [*active[start:], module]
        if module in visited:
            return []
        visited.add(module)
        active.append(module)
        active_set.add(module)
        for dependency in sorted(graph[module]):
            found = visit(dependency)
            if found:
                return found
        active.pop()
        active_set.remove(module)
        return []

    for module in sorted(graph):
        found = visit(module)
        if found:
            return found
    return []


def _python_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        yield from root.rglob("*.py")


def test_active_python_import_graph_has_no_static_cycles() -> None:
    modules = _active_modules()
    known = set(modules)
    graph = {
        name: _import_targets(path, name, known) for name, path in modules.items()
    }
    assert not (found := _cycle(graph)), " -> ".join(found)


def test_package_does_not_import_legacy_tool_modules() -> None:
    legacy_names = {path.stem for path in TOOLS_ROOT.glob("*.py")}
    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                if name in legacy_names:
                    violations.append(f"{path.relative_to(ROOT)} imports {name}")
    assert violations == []


def test_core_and_domain_models_respect_dependency_direction() -> None:
    modules = _active_modules()
    known = set(modules)
    violations: list[str] = []
    for name, path in modules.items():
        if not name.startswith("career_job_search."):
            continue
        targets = _import_targets(path, name, known)
        if name.startswith("career_job_search.core."):
            forbidden = {
                target
                for target in targets
                if target.startswith("career_job_search.")
                and not target.startswith("career_job_search.core.")
            }
        elif name.endswith(".models") or name.endswith("_models"):
            forbidden = {
                target
                for target in targets
                if target.startswith(
                    (
                        "career_job_search.automation.",
                        "career_job_search.dev_agents.",
                        "career_job_search.integrations.",
                        "career_job_search.workspace.",
                    )
                )
            }
        else:
            forbidden = set()
        violations.extend(
            f"{path.relative_to(ROOT)} imports {target}"
            for target in sorted(forbidden)
        )
    assert violations == []


def test_production_python_modules_stay_bounded() -> None:
    violations: list[str] = []
    for path in _python_files(
        [ROOT / "src", ROOT / "tools", ROOT / "cv", ROOT / "mcp"]
    ):
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > MAX_PRODUCTION_MODULE_LINES:
            violations.append(f"{path.relative_to(ROOT)}: {line_count} lines")
    assert violations == []


def test_tools_are_thin_compatibility_adapters() -> None:
    violations = [
        f"{path.relative_to(ROOT)}: {line_count} lines"
        for path in sorted(TOOLS_ROOT.glob("*.py"))
        if (line_count := len(path.read_text(encoding="utf-8").splitlines()))
        > MAX_TOOL_WRAPPER_LINES
    ]
    assert violations == []


def test_tracked_top_level_structure_is_expected() -> None:
    expected = {
        ".cursor",
        ".github",
        ".memory",
        "archive",
        "config",
        "cv",
        "dashboard",
        "docs",
        "inbox",
        "linkedin",
        "mcp",
        "packs",
        "pipeline",
        "plans",
        "prompts",
        "raycast-job-search-hub",
        "scripts",
        "src",
        "tests",
        "tools",
    }
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    actual = {
        line.split("/", 1)[0]
        for line in completed.stdout.splitlines()
        if "/" in line
    }
    assert actual == expected


def test_live_dispatch_limit_has_one_active_assignment() -> None:
    assignments: list[tuple[Path, object]] = []
    for path in _python_files([ROOT / "src", ROOT / "tools", ROOT / "cv", ROOT / "mcp"]):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                names = [target.id for target in node.targets if isinstance(target, ast.Name)]
                value = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
                value = node.value
            else:
                continue
            if "MAX_LIVE_DISPATCH" in names:
                assignments.append((path.relative_to(ROOT), ast.literal_eval(value)))
    assert assignments == [(Path("src/career_job_search/core/limits.py"), 3)]


def test_root_dependency_sources_are_unambiguous() -> None:
    assert (ROOT / "pyproject.toml").is_file()
    assert (ROOT / "uv.lock").is_file()
    assert not (ROOT / "requirements.txt").exists()
    assert not (ROOT / "requirements-dev.txt").exists()


def test_cv_catalogue_is_versioned_unique_and_complete() -> None:
    catalogue = load_cv_catalogue()
    assert catalogue.schema_version == "cv_catalogue_v1"
    assert len(catalogue.variants) == 6
    assert len({variant.slug for variant in catalogue.variants}) == 6
    for variant in catalogue.variants:
        assert variant.name and variant.focus and variant.pdf_stem
        assert (ROOT / "cv" / variant.source_filename).is_file()


def test_cv_catalogue_helper_uses_versioned_envelopes() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / "src"), env.get("PYTHONPATH", "")])
    )
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "cv_catalogue.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["schema"] == "career_python_helper_v1"
    assert payload["ok"] is True
    assert payload["data"]["schema"] == "cv_catalogue_v1"
