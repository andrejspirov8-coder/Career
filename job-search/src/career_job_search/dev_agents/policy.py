"""Task, path, snapshot, and verification policy for local agents."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from career_job_search.dev_agents.common import (
    SAFE_NPM_COMMANDS,
    SENSITIVE_OBJECTIVE_TERMS,
    SENSITIVE_SNAPSHOT_BASENAMES,
    SENSITIVE_SNAPSHOT_SUFFIXES,
    WRITE_FORBIDDEN_PATHS,
    CoordinatorError,
)
from career_job_search.dev_agents.models import (
    AgentTaskSpec,
    LocalAgentSettings,
    VerificationCheck,
    normalise_relative_path,
)


def _path_matches(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(f"{prefix}/")


def is_snapshot_forbidden(path: str, settings: LocalAgentSettings) -> bool:
    clean = normalise_relative_path(path)
    lower = clean.casefold()
    parts = lower.split("/")
    basename = parts[-1]
    if any(part.startswith(".env") for part in parts):
        return True
    if basename in SENSITIVE_SNAPSHOT_BASENAMES:
        return True
    if basename.endswith(SENSITIVE_SNAPSHOT_SUFFIXES):
        return True
    if any(
        marker in basename
        for marker in ("client_secret", "credential", "private_key", "refresh_token")
    ):
        return True
    if any("browser-profile" in part or "browser_profile" in part for part in parts):
        return True
    if lower.endswith(".pdf"):
        return True
    if any(
        part in {item.casefold() for item in settings.snapshot.forbidden_parts}
        for part in parts
    ):
        return True
    return any(
        _path_matches(lower, prefix.casefold())
        for prefix in settings.snapshot.forbidden_prefixes
    )


def is_write_forbidden(path: str) -> bool:
    clean = normalise_relative_path(path)
    lower = clean.casefold()
    return any(
        _path_matches(lower, prefix.casefold()) for prefix in WRITE_FORBIDDEN_PATHS
    )


def path_is_allowed(path: str, allowed_paths: Sequence[str]) -> bool:
    clean = normalise_relative_path(path)
    return any(
        allowed == "." or clean == allowed or clean.startswith(f"{allowed}/")
        for allowed in allowed_paths
    )


def validate_check(check: VerificationCheck) -> None:
    executable = Path(check.argv[0]).name
    args = tuple(check.argv[1:])
    if executable in {"python", "python3"}:
        if len(args) < 2 or args[0] != "-m" or args[1] not in {"pytest", "ruff"}:
            raise CoordinatorError(
                f"Check {check.name!r} may run only python -m pytest/ruff."
            )
        return
    if executable == "npm":
        command = args[:2] if args[:1] == ("run",) else args[:1]
        if command not in SAFE_NPM_COMMANDS:
            raise CoordinatorError(
                f"Check {check.name!r} uses an unsupported npm command."
            )
        return
    raise CoordinatorError(
        f"Check {check.name!r} uses unsupported executable: {executable}"
    )


def validate_task_policy(task: AgentTaskSpec, *, settings: LocalAgentSettings) -> None:
    if task.risk == "high":
        raise CoordinatorError("High-risk work must stay with Main Codex.")
    if task.max_changed_files > settings.limits.max_changed_files:
        raise CoordinatorError("Task exceeds the configured changed-file limit.")
    if task.max_diff_lines > settings.limits.max_diff_lines:
        raise CoordinatorError("Task exceeds the configured diff-line limit.")
    if task.role == "implementer":
        objective = task.objective.casefold()
        if any(term in objective for term in SENSITIVE_OBJECTIVE_TERMS):
            raise CoordinatorError(
                "Sensitive authentication, migration, deployment, dependency, "
                "LinkedIn-send, or Git-history work must stay with Main Codex."
            )
        for path in task.allowed_paths:
            if is_snapshot_forbidden(path, settings) or is_write_forbidden(path):
                raise CoordinatorError(
                    f"Local implementers cannot modify protected path: {path}"
                )
    for check in task.acceptance_checks:
        validate_check(check)
