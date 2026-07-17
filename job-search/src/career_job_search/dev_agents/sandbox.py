"""Network, process, and environment sandbox construction for local agents."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from career_job_search.dev_agents.common import (
    MAX_STREAM_CHARS,
    CoordinatorError,
    CoordinatorPaths,
    atomic_write_json,
)
from career_job_search.dev_agents.models import LocalAgentSettings


def _seatbelt_string(value: Path | str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _seatbelt_home_filter(real_home: Path, exceptions: set[Path]) -> str:
    """Match the real home directory while excluding registered safe subpaths."""

    filters = [f"(subpath {_seatbelt_string(real_home)})"]
    filters.extend(
        f"(require-not (subpath {_seatbelt_string(path)}))"
        for path in sorted(exceptions, key=str)
        if path.exists()
    )
    return "(require-all " + " ".join(filters) + ")"


def build_sandbox_profile(
    *,
    worktree: Path,
    run_dir: Path,
    paths: CoordinatorPaths,
    allow_worktree_writes: bool,
) -> str:
    """Build a macOS Seatbelt profile with local-Ollama-only networking."""

    real_home = Path.home().resolve()
    read_paths = {
        worktree.resolve(),
        run_dir.resolve(),
        (paths.repo_root / ".venv").resolve(),
        (paths.repo_root / "dashboard" / "node_modules").resolve(),
        (paths.repo_root / "raycast-job-search-hub" / "node_modules").resolve(),
        (real_home / ".local" / "share" / "uv" / "python").resolve(),
    }
    write_paths = {run_dir.resolve()}
    if allow_worktree_writes:
        write_paths.add(worktree.resolve())

    read_filter = _seatbelt_home_filter(real_home, read_paths)
    write_filter = _seatbelt_home_filter(real_home, write_paths)

    lines = [
        "(version 1)",
        "(allow default)",
        "(deny network-outbound)",
        '(allow network-outbound (remote ip "localhost:11434"))',
        f"(deny file-read-data {read_filter})",
        f"(deny file-map-executable {read_filter})",
        f"(deny file-write* {write_filter})",
    ]
    lines.extend(
        f"(allow file-read* (subpath {_seatbelt_string(path)}))"
        for path in sorted(read_paths, key=str)
        if path.exists()
    )
    lines.extend(
        f"(allow file-write* (subpath {_seatbelt_string(path)}))"
        for path in sorted(write_paths, key=str)
    )
    lines.append(
        f"(deny file-write* (subpath {_seatbelt_string(worktree.resolve() / '.git')}))"
    )
    return "\n".join(lines) + "\n"


def _exec_rules() -> str:
    forbidden: list[tuple[list[str | list[str]], str]] = [
        (
            [
                "git",
                [
                    "add",
                    "am",
                    "apply",
                    "branch",
                    "checkout",
                    "clean",
                    "commit",
                    "fetch",
                    "merge",
                    "pull",
                    "push",
                    "rebase",
                    "reset",
                    "restore",
                    "switch",
                    "tag",
                    "worktree",
                ],
            ],
            "Git mutations are controlled by the coordinator; use read-only inspection instead.",
        ),
        (
            ["npm", ["ci", "install", "uninstall", "update"]],
            "Dependency installation is disabled; use the existing locked node_modules.",
        ),
        (
            ["uv", ["add", "lock", "remove", "sync"]],
            "Dependency installation is disabled; use the existing locked environment.",
        ),
        (
            ["python", "-m", "pip"],
            "Package installation is disabled; use the existing locked environment.",
        ),
        (
            ["python3", "-m", "pip"],
            "Package installation is disabled; use the existing locked environment.",
        ),
        (
            [["pip", "pip3"], "install"],
            "Package installation is disabled; use the existing locked environment.",
        ),
        (
            [["rm", "rmdir", "mv"]],
            "File deletion and renaming require Main Codex and user review.",
        ),
        (
            [["curl", "wget", "nc", "ssh", "scp", "gh"]],
            "External network tools are disabled; the local agent is offline.",
        ),
        (
            [["open", "osascript"]],
            "Local agents may not control desktop applications or browsers.",
        ),
        (
            ["make", ["scout", "dispatch-dry", "daily-dry", "daily-queue"]],
            "Job-search and LinkedIn actions are outside development-agent scope.",
        ),
        (
            ["python", "tools/linkedin_recruiter_bot.py"],
            "LinkedIn actions are outside development-agent scope.",
        ),
        (
            ["python", "tools/recruiter_orchestrate.py"],
            "Recruiter execution is outside development-agent scope.",
        ),
    ]
    blocks: list[str] = []
    for pattern, justification in forbidden:
        blocks.append(
            "prefix_rule(\n"
            f"    pattern = {pattern!r},\n"
            '    decision = "forbidden",\n'
            f"    justification = {justification!r},\n"
            ")"
        )
    return "\n\n".join(blocks) + "\n"


def safe_agent_environment(
    *, home: Path, codex_home: Path, temp_dir: Path, settings: LocalAgentSettings
) -> dict[str, str]:
    return {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(home),
        "CODEX_HOME": str(codex_home),
        "TMPDIR": str(temp_dir),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "OLLAMA_HOST": settings.ollama_host,
        "GIT_OPTIONAL_LOCKS": "0",
        "NO_COLOR": "1",
        "CI": "1",
        "NEXT_TELEMETRY_DISABLED": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONNOUSERSITE": "1",
    }


def _redact_stream(value: str) -> str:
    clean = value[:MAX_STREAM_CHARS]
    for key, secret in os.environ.items():
        if (
            secret
            and len(secret) >= 8
            and any(
                term in key.casefold()
                for term in ("key", "secret", "token", "password")
            )
        ):
            clean = clean.replace(secret, "<redacted>")
    clean = re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password)\b(\s*[:=]\s*)([^\s,;}]+)",
        r"\1\2<redacted>",
        clean,
    )
    return clean


def write_model_catalog(
    path: Path, *, model: str, settings: LocalAgentSettings
) -> None:
    model_settings = settings.models.get(model)
    if model_settings is None:
        raise CoordinatorError(f"No local model metadata configured for {model}.")
    atomic_write_json(
        path,
        {
            "models": [
                {
                    "base_instructions": "",
                    "context_window": model_settings.context_window,
                    "default_verbosity": "low",
                    "display_name": model,
                    "experimental_supported_tools": [],
                    "input_modalities": ["text"],
                    "priority": 0,
                    "shell_type": "default",
                    "slug": model,
                    "support_verbosity": True,
                    "supported_in_api": True,
                    "supported_reasoning_levels": [],
                    "supports_parallel_tool_calls": False,
                    "supports_reasoning_summaries": False,
                    "truncation_policy": {"limit": 4000, "mode": "bytes"},
                    "visibility": "list",
                }
            ]
        },
    )
