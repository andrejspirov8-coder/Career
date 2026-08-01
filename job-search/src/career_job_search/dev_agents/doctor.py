"""Local-agent environment diagnosis and model identity checks."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from career_job_search.dev_agents.common import (
    CoordinatorError,
    CoordinatorPaths,
    atomic_write_text,
    utc_now_iso,
)
from career_job_search.dev_agents.execution import _ollama_model_identities
from career_job_search.dev_agents.models import LocalAgentSettings
from career_job_search.dev_agents.runs import get_rollout
from career_job_search.dev_agents.sandbox import build_sandbox_profile
from career_job_search.dev_agents.snapshots import _git


def _doctor_check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _ollama_models(settings: LocalAgentSettings) -> set[str]:
    return set(_ollama_model_identities(settings))


def _ollama_model_context(model: str, settings: LocalAgentSettings) -> int:
    body = json.dumps({"model": model}).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310
        f"{settings.ollama_host}/api/show",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - settings validation fixes this to 127.0.0.1
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise CoordinatorError(
            f"Could not inspect Ollama model {model}: {exc}"
        ) from exc
    values = [
        int(value)
        for key, value in payload.get("model_info", {}).items()
        if key.endswith(".context_length") and isinstance(value, int)
    ]
    if not values:
        raise CoordinatorError(f"Ollama did not report a context length for {model}.")
    return max(values)


def doctor(*, settings: LocalAgentSettings, paths: CoordinatorPaths) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(
        _doctor_check(
            "platform",
            platform.system() == "Darwin",
            f"{platform.system()} {platform.machine()}",
        )
    )
    for command in ("codex", "ollama", "git", "sandbox-exec"):
        location = shutil.which(command)
        checks.append(
            _doctor_check(
                f"command:{command}",
                bool(location),
                location or "not found",
            )
        )
    git_root = _git(
        ["rev-parse", "--show-toplevel"], cwd=paths.repo_root, check=False
    ).stdout.strip()
    checks.append(
        _doctor_check(
            "repository",
            Path(git_root).resolve() == paths.repo_root.resolve()
            if git_root
            else False,
            git_root or "not a Git repository",
        )
    )
    dependency_paths = (
        paths.repo_root / ".venv" / "bin" / "python",
        paths.repo_root / "dashboard" / "node_modules",
        paths.repo_root / "raycast-job-search-hub" / "node_modules",
    )
    for dependency in dependency_paths:
        checks.append(
            _doctor_check(
                f"dependency:{dependency.relative_to(paths.repo_root)}",
                dependency.exists(),
                "available" if dependency.exists() else "run make bootstrap",
            )
        )
    try:
        installed_identities = _ollama_model_identities(settings)
        checks.append(_doctor_check("ollama", True, "local service is responding"))
        for model in settings.models:
            installed = model in installed_identities
            checks.append(
                _doctor_check(
                    f"model:{model}",
                    installed,
                    "installed" if installed else "not installed",
                )
            )
            if installed:
                actual_digest = installed_identities[model]
                expected_digest = settings.models[model].digest
                checks.append(
                    _doctor_check(
                        f"model-digest:{model}",
                        actual_digest == expected_digest,
                        (
                            f"{actual_digest[:12]} matches configuration"
                            if actual_digest == expected_digest
                            else f"expected {expected_digest[:12]}, found {actual_digest[:12]}"
                        ),
                    )
                )
                available_context = _ollama_model_context(model, settings)
                requested_context = settings.models[model].context_window
                checks.append(
                    _doctor_check(
                        f"model-context:{model}",
                        available_context >= requested_context,
                        f"{available_context} available; {requested_context} configured",
                    )
                )
    except CoordinatorError as exc:
        checks.append(_doctor_check("ollama", False, str(exc)))

    sandbox_exec = shutil.which("sandbox-exec")
    if platform.system() == "Darwin" and sandbox_exec:
        doctor_dir = paths.runtime_root / "doctor"
        doctor_dir.mkdir(parents=True, exist_ok=True)
        probe_worktree = doctor_dir / "worktree"
        probe_worktree.mkdir(parents=True, exist_ok=True)
        probe_file = probe_worktree / "visible.txt"
        atomic_write_text(probe_file, "sandbox probe\n")
        profile_path = doctor_dir / "doctor.sb"
        atomic_write_text(
            profile_path,
            build_sandbox_profile(
                worktree=probe_worktree,
                run_dir=doctor_dir,
                paths=paths,
                allow_worktree_writes=False,
            ),
        )
        worktree_probe = subprocess.run(
            [sandbox_exec, "-f", str(profile_path), "/bin/cat", str(probe_file)],  # noqa: S603
            capture_output=True,
            check=False,
        )
        checks.append(
            _doctor_check(
                "sandbox:snapshot-read",
                worktree_probe.returncode == 0,
                "allowed" if worktree_probe.returncode == 0 else "blocked",
            )
        )
        active_probe = subprocess.run(
            [  # noqa: S603
                sandbox_exec,
                "-f",
                str(profile_path),
                "/bin/cat",
                str(paths.repo_root / "pyproject.toml"),
            ],
            capture_output=True,
            check=False,
        )
        checks.append(
            _doctor_check(
                "sandbox:active-workspace",
                active_probe.returncode != 0,
                "blocked" if active_probe.returncode != 0 else "unexpectedly readable",
            )
        )
        local_probe = subprocess.run(
            [  # noqa: S603
                sandbox_exec,
                "-f",
                str(profile_path),
                "/usr/bin/curl",
                "-fsS",
                "--max-time",
                "3",
                f"{settings.ollama_host.rstrip('/')}/api/tags",
            ],
            capture_output=True,
            check=False,
        )
        checks.append(
            _doctor_check(
                "sandbox:local-ollama",
                local_probe.returncode == 0,
                "allowed" if local_probe.returncode == 0 else "blocked or unavailable",
            )
        )
        external_probe = subprocess.run(
            [  # noqa: S603
                sandbox_exec,
                "-f",
                str(profile_path),
                "/usr/bin/curl",
                "-fsS",
                "--max-time",
                "2",
                "https://chatgpt.com/",
            ],
            capture_output=True,
            check=False,
        )
        checks.append(
            _doctor_check(
                "sandbox:external-network",
                external_probe.returncode != 0,
                "blocked"
                if external_probe.returncode != 0
                else "unexpectedly reachable",
            )
        )
        sensitive = Path.home() / ".codex" / "config.toml"
        if sensitive.exists():
            read_probe = subprocess.run(
                [  # noqa: S603
                    sandbox_exec,
                    "-f",
                    str(profile_path),
                    "/bin/cat",
                    str(sensitive),
                ],
                capture_output=True,
                check=False,
            )
            checks.append(
                _doctor_check(
                    "sandbox:home-secrets",
                    read_probe.returncode != 0,
                    "blocked"
                    if read_probe.returncode != 0
                    else "unexpectedly readable",
                )
            )
    rollout = get_rollout(settings=settings, db_path=paths.db_path)
    checks.append(
        _doctor_check(
            "qualification",
            bool(rollout.get("qualified_at")),
            (
                f"qualified with {rollout.get('selected_implementer_model')}"
                if rollout.get("qualified_at")
                else "run the benchmark before local writing"
            ),
        )
    )
    required_checks = [item for item in checks if item["name"] != "qualification"]
    return {
        "schema": "career_local_dev_agent_doctor_v1",
        "ok": all(item["ok"] for item in required_checks),
        "generated_at": utc_now_iso(),
        "checks": checks,
        "rollout": rollout,
    }
