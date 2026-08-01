"""Architectural boundary validation for local development agents."""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

# Layer hierarchy: inner (0) → outer (higher). Dependencies must flow inward only.
LAYERS = [
    ("core", "src/career_job_search/core"),
    ("domain", "src/career_job_search/domain"),
    ("application", "src/career_job_search/application"),
    ("infrastructure", "src/career_job_search/infrastructure"),
    ("dev_agents", "src/career_job_search/dev_agents"),
    ("ui_dashboard", "dashboard"),
    ("tools_linkedin", "tools/linkedin"),
    ("tools_other", "tools"),
    ("cv", "cv"),
]

# (importer_layer, forbidden_imported_layer) — inner layers must not import outer layers
FORBIDDEN_INWARD_IMPORTS = {
    ("domain", "infrastructure"),
    ("domain", "ui_dashboard"),
    ("domain", "tools_linkedin"),
    ("application", "ui_dashboard"),
    ("core", "domain"),
    ("core", "application"),
    ("core", "infrastructure"),
    ("core", "ui_dashboard"),
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
        file_path = repo_root / file_str
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


def main(argv: list[str] | None = None) -> int:
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


if __name__ == "__main__":
    sys.exit(main())