"""Local Codex/Ollama process execution and deterministic verification."""

from __future__ import annotations

import fcntl
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from career_job_search.dev_agents.common import (
    CODEX_INNER_SANDBOX_MODE,
    EXEC_POLICY_REJECTION_MARKERS,
    AgentProcessError,
    CoordinatorError,
    CoordinatorPaths,
    PatchInfo,
    StructuredResponse,
    atomic_write_json,
    atomic_write_text,
    utc_now_iso,
)
from career_job_search.dev_agents.models import (
    AgentFinding,
    AgentResponse,
    AgentRole,
    AgentTaskSpec,
    CheckResult,
    LocalAgentSettings,
    VerificationCheck,
)
from career_job_search.dev_agents.policy import validate_check
from career_job_search.dev_agents.runs import (
    _update_run,
    connect,
    get_rollout,
    get_run,
)
from career_job_search.dev_agents.sandbox import (
    _exec_rules,
    _redact_stream,
    build_sandbox_profile,
    safe_agent_environment,
    write_model_catalog,
)


def _ollama_model_identities(settings: LocalAgentSettings) -> dict[str, str]:
    request = urllib.request.Request(
        f"{settings.ollama_host.rstrip('/')}/api/tags",
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:  # noqa: S310 - fixed localhost URL from validated repository config
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise CoordinatorError(f"Ollama is unavailable: {exc}") from exc
    models = payload.get("models", [])
    return {
        str(item.get("name") or item.get("model")): str(item.get("digest") or "")
        for item in models
        if item.get("name") or item.get("model")
    }


def _is_cancel_requested(task_id: str, *, db_path: Path) -> bool:
    with connect(db_path) as con:
        row = con.execute(
            "SELECT cancel_requested FROM local_agent_runs WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    return bool(row and row["cancel_requested"])


@contextmanager
def serial_model_slot(paths: CoordinatorPaths) -> Iterator[None]:
    """Allow only one Codex/Ollama model process at a time across all workers."""

    paths.runtime_root.mkdir(parents=True, exist_ok=True)
    lock_path = paths.runtime_root / "model-process.lock"
    with lock_path.open("a+b") as lock_file:
        lock_path.chmod(0o600)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def run_agent_process(
    *,
    task_id: str,
    role: AgentRole,
    model: str,
    label: str,
    prompt: str,
    worktree: Path,
    run_dir: Path,
    timeout_seconds: int,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
    response_model: type[StructuredResponse] = AgentResponse,
) -> StructuredResponse:
    """Run one isolated local Codex process and validate its final response."""

    process_dir = run_dir / label
    codex_home = process_dir / "codex-home"
    synthetic_home = process_dir / "home"
    temp_dir = process_dir / "tmp"
    rules_dir = codex_home / "rules"
    for directory in (process_dir, codex_home, synthetic_home, temp_dir, rules_dir):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)

    schema_path = process_dir / "agent-response.schema.json"
    response_path = process_dir / "response.json"
    catalog_path = process_dir / "model-catalog.json"
    profile_path = process_dir / "offline.sb"
    stdout_path = process_dir / "stdout.jsonl"
    stderr_path = process_dir / "stderr.log"
    atomic_write_json(schema_path, response_model.model_json_schema())
    write_model_catalog(catalog_path, model=model, settings=settings)
    atomic_write_text(rules_dir / "local-agent.rules", _exec_rules())
    atomic_write_text(
        profile_path,
        build_sandbox_profile(
            worktree=worktree,
            run_dir=run_dir,
            paths=paths,
            allow_worktree_writes=role == "implementer",
        ),
    )

    sandbox_exec = shutil.which("sandbox-exec")
    codex = shutil.which("codex")
    if platform.system() != "Darwin" or not sandbox_exec:
        raise AgentProcessError(
            "The required macOS network/filesystem sandbox is unavailable.",
            status="blocked",
        )
    if not codex:
        raise AgentProcessError("Codex CLI is unavailable.", status="blocked")

    command = [
        sandbox_exec,
        "-f",
        str(profile_path),
        codex,
        "exec",
        "--oss",
        "--local-provider",
        "ollama",
        "--model",
        model,
        "--ephemeral",
        "--ignore-user-config",
        "--sandbox",
        # macOS cannot apply Codex's Seatbelt profile from inside our stricter
        # process-wide Seatbelt profile. The outer profile below remains the
        # effective read/write and network boundary for every child process.
        CODEX_INNER_SANDBOX_MODE,
        "--cd",
        str(worktree),
    ]
    if settings.models[model].use_cli_output_schema:
        command.extend(["--output-schema", str(schema_path)])
    command.extend(
        [
            "--output-last-message",
            str(response_path),
            "--json",
            "--color",
            "never",
        ]
    )
    command.extend(
        [
            "-c",
            'approval_policy="never"',
            "-c",
            "sandbox_workspace_write.network_access=false",
            "-c",
            "allow_login_shell=false",
            "-c",
            f"model_catalog_json={json.dumps(str(catalog_path))}",
            "-c",
            f"model_context_window={settings.models[model].context_window}",
            "-c",
            "tool_output_token_limit=2000",
            "-c",
            "analytics.enabled=false",
            "-c",
            "feedback.enabled=false",
            "-c",
            "features.apps=false",
            "-c",
            "features.goals=false",
            "-c",
            "features.hooks=false",
            "-c",
            "features.memories=false",
            "-c",
            "features.multi_agent=false",
            "-c",
            "features.remote_plugin=false",
            "-c",
            "features.skill_mcp_dependency_install=false",
            "-c",
            'web_search="disabled"',
            "-c",
            'otel.exporter="none"',
            "-c",
            'shell_environment_policy.include_only=["PATH","HOME","TMPDIR","LANG","LC_ALL","OLLAMA_HOST","GIT_OPTIONAL_LOCKS","NO_COLOR","CI","NEXT_TELEMETRY_DISABLED"]',
            "-",
        ]
    )
    environment = safe_agent_environment(
        home=synthetic_home,
        codex_home=codex_home,
        temp_dir=temp_dir,
        settings=settings,
    )
    with serial_model_slot(paths):
        if _is_cancel_requested(task_id, db_path=paths.db_path):
            raise AgentProcessError(
                "Local-agent run was cancelled.", status="cancelled"
            )
        process = subprocess.Popen(
            command,
            cwd=worktree,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        _update_run(
            task_id,
            db_path=paths.db_path,
            child_pid=process.pid,
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(prompt, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=3)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout, stderr = process.communicate()
        finally:
            _update_run(task_id, db_path=paths.db_path, child_pid=None)

    atomic_write_text(stdout_path, _redact_stream(stdout))
    atomic_write_text(stderr_path, _redact_stream(stderr))
    if timed_out:
        raise AgentProcessError(
            f"Local {role} timed out after {timeout_seconds} seconds.",
            status="timed_out",
        )
    if _is_cancel_requested(task_id, db_path=paths.db_path):
        raise AgentProcessError("Local-agent run was cancelled.", status="cancelled")
    if process.returncode != 0:
        message = _redact_stream(stderr).strip().splitlines()
        detail = message[-1] if message else f"exit code {process.returncode}"
        raise AgentProcessError(f"Local {role} failed: {detail}")
    if not response_path.is_file():
        raise AgentProcessError(f"Local {role} returned no structured response.")
    try:
        return load_structured_response(response_path, response_model)
    except (OSError, ValidationError) as exc:
        raise AgentProcessError(
            f"Local {role} returned invalid structured output: {exc}"
        ) from exc


def find_agent_policy_rejections(run_dir: Path) -> list[str]:
    """Return blocked forbidden-command attempts from model process logs."""

    rejections: list[str] = []
    for log_path in sorted(run_dir.glob("*/stderr.log")):
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if any(marker in line for marker in EXEC_POLICY_REJECTION_MARKERS):
                rendered = f"{log_path.parent.name}: {_redact_stream(line)[:1000]}"
                if rendered not in rejections:
                    rejections.append(rendered)
            if len(rejections) >= 10:
                return rejections
    return rejections


def load_structured_response(
    response_path: Path, response_model: type[StructuredResponse]
) -> StructuredResponse:
    """Validate raw JSON or one otherwise-empty fenced JSON response."""

    raw = response_path.read_text(encoding="utf-8").strip()
    try:
        return response_model.model_validate_json(raw)
    except ValidationError as first_error:
        fenced = re.fullmatch(
            r"```(?:json)?[ \t]*\r?\n(?P<body>.*)\r?\n```",
            raw,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if fenced is None:
            raise first_error
        return response_model.model_validate_json(fenced.group("body").strip())


def agent_response_search_text(response: AgentResponse) -> str:
    """Flatten all non-blocking response prose for deterministic qualification."""

    values = [response.summary, *response.details]
    for finding in response.findings:
        values.extend((finding.title, finding.detail))
    return " ".join(values).casefold()


def build_agent_prompt(
    task: AgentTaskSpec,
    *,
    role: AgentRole,
    patch: str = "",
    reviewer_feedback: Sequence[AgentFinding] = (),
) -> str:
    instructions = [
        "You are a fully local development agent working in a disposable snapshot.",
        "Never access paths outside the current worktree, credentials, user state, browsers, or network services.",
        "Never install dependencies, change Git history/index/branches, commit, push, delete, or rename files.",
        "Use only the task's allowed paths. The coordinator independently checks every change and runs acceptance checks.",
        "Use shell tools with their default permissions only. Never request escalated permissions.",
        "Do not create a plan, todo list, goal, subagent, or follow-up. Perform the bounded task in this turn.",
        "Read the relevant allowed files before deciding.",
        "Keep command output small. Never run recursive directory listings; prefer rg with explicit paths and limits.",
        "If you run an existing Python check, use .venv/bin/python. If the linked locked dependency is unavailable, return blocked; never search other environments or install a package.",
        "Do not stop after acknowledging the task. Continue until the work is complete or return status=blocked with a concrete reason.",
        (
            "Return only one JSON object with exactly these fields: "
            "schema_version, status, summary, details, risks, blocking_reason, "
            "findings, requested_checks. Use schema_version="
            "career_local_dev_agent_response_v1."
        ),
        (
            'Completed example: {"schema_version":"career_local_dev_agent_response_v1",'
            '"status":"completed","summary":"concise result","details":[],"risks":[],'
            '"blocking_reason":null,"findings":[],"requested_checks":[]}'
        ),
    ]
    if role == "implementer":
        instructions.append(
            "Implement the objective now. You may edit existing files or add text files only inside allowed_paths. "
            "This local OSS router does not provide apply_patch: use its shell command tool with a small, deterministic "
            "python -c, perl, or sed edit, then inspect the result with git diff. Never call apply_patch."
        )
    else:
        instructions.append("This role is read-only. Do not edit any files.")
    if role == "reviewer":
        instructions.append(
            "Review the patch for correctness, scope, security, regressions, and missing tests. Use critical/major only for actionable blockers."
        )
        instructions.append(
            'Reviewer finding example: {"severity":"major","title":"Shell injection",'
            '"detail":"Untrusted input reaches a shell.","path":"runner.py","line":4}. '
            "Return findings as objects in exactly that shape, never as strings."
        )
    payload: dict[str, Any] = {
        "instructions": instructions,
        "task": task.model_dump(mode="json"),
    }
    if patch:
        payload["patch"] = patch
    if reviewer_feedback:
        payload["reviewer_feedback_to_fix"] = [
            finding.model_dump(mode="json") for finding in reviewer_feedback
        ]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _resolve_check_command(
    check: VerificationCheck, *, paths: CoordinatorPaths
) -> list[str]:
    executable = Path(check.argv[0]).name
    if executable in {"python", "python3"}:
        python = paths.repo_root / ".venv" / "bin" / "python"
        if not python.exists():
            raise CoordinatorError(
                "The locked Python environment is missing. Run make bootstrap outside the local agent."
            )
        return [str(python), *check.argv[1:]]
    if executable == "npm":
        npm = shutil.which("npm")
        if not npm:
            raise CoordinatorError("npm is unavailable.")
        return [npm, *check.argv[1:]]
    raise CoordinatorError(f"Unsupported check executable: {executable}")


def run_checks(
    checks: Sequence[VerificationCheck],
    *,
    worktree: Path,
    run_dir: Path,
    task_id: str,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
) -> list[CheckResult]:
    if not checks:
        return []
    profile_path = run_dir / "verification.sb"
    atomic_write_text(
        profile_path,
        build_sandbox_profile(
            worktree=worktree,
            run_dir=run_dir,
            paths=paths,
            allow_worktree_writes=True,
        ),
    )
    sandbox_exec = shutil.which("sandbox-exec")
    if platform.system() != "Darwin" or not sandbox_exec:
        raise CoordinatorError(
            "The required macOS verification sandbox is unavailable."
        )
    check_home = run_dir / "check-home"
    check_tmp = run_dir / "check-tmp"
    check_codex_home = run_dir / "check-codex-home"
    for directory in (check_home, check_tmp, check_codex_home):
        directory.mkdir(parents=True, exist_ok=True)
    environment = safe_agent_environment(
        home=check_home,
        codex_home=check_codex_home,
        temp_dir=check_tmp,
        settings=settings,
    )
    results: list[CheckResult] = []
    for check in checks:
        if _is_cancel_requested(task_id, db_path=paths.db_path):
            results.append(
                CheckResult(
                    name=check.name,
                    argv=check.argv,
                    cwd=check.cwd,
                    status="cancelled",
                    duration_seconds=0,
                )
            )
            break
        validate_check(check)
        cwd = (worktree / check.cwd).resolve()
        if not cwd.is_relative_to(worktree.resolve()) or not cwd.is_dir():
            raise CoordinatorError(f"Check directory does not exist: {check.cwd}")
        command = [
            sandbox_exec,
            "-f",
            str(profile_path),
            *_resolve_check_command(check, paths=paths),
        ]
        started = time.monotonic()
        try:
            process = subprocess.run(
                command,
                cwd=cwd,
                env=environment,
                text=True,
                capture_output=True,
                timeout=check.timeout_seconds,
                check=False,
            )
            status = "passed" if process.returncode == 0 else "failed"
            result = CheckResult(
                name=check.name,
                argv=check.argv,
                cwd=check.cwd,
                status=status,
                exit_code=process.returncode,
                duration_seconds=round(time.monotonic() - started, 3),
                stdout=_redact_stream(process.stdout),
                stderr=_redact_stream(process.stderr),
            )
        except subprocess.TimeoutExpired as exc:
            result = CheckResult(
                name=check.name,
                argv=check.argv,
                cwd=check.cwd,
                status="timed_out",
                duration_seconds=round(time.monotonic() - started, 3),
                stdout=_redact_stream(exc.stdout or ""),
                stderr=_redact_stream(exc.stderr or ""),
            )
        results.append(result)
        if result.status != "passed":
            break
    return results


def _selected_implementer_identity(
    *, settings: LocalAgentSettings, paths: CoordinatorPaths
) -> tuple[str, str]:
    rollout = get_rollout(settings=settings, db_path=paths.db_path)
    model = rollout.get("selected_implementer_model")
    digest = rollout.get("selected_implementer_digest")
    if (
        not rollout.get("qualified_at")
        or not isinstance(model, str)
        or not model
        or not isinstance(digest, str)
        or not digest
    ):
        raise CoordinatorError(
            "Local writing is disabled until `local_dev_agents.py benchmark` passes."
        )
    if model not in settings.models:
        raise CoordinatorError(
            f"Qualified implementer model is no longer configured: {model}"
        )
    if settings.models[model].digest != digest:
        raise CoordinatorError(
            f"Qualified model digest no longer matches configuration: {model}"
        )
    installed = _ollama_model_identities(settings)
    if installed.get(model) != digest:
        raise CoordinatorError(
            f"Model {model} changed or is unavailable; requalification is required."
        )
    return model, digest


def _run_with_process_retry(
    *,
    task_id: str,
    role: AgentRole,
    model: str,
    label_prefix: str,
    prompt: str,
    worktree: Path,
    run_dir: Path,
    timeout_seconds: int,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
    attempts_remaining: int,
) -> tuple[AgentResponse, int]:
    last_error: AgentProcessError | None = None
    tries = min(attempts_remaining + 1, 2)
    current_prompt = prompt
    for offset in range(tries):
        attempt_number = 2 - attempts_remaining + offset
        _update_run(
            task_id,
            db_path=paths.db_path,
            attempt=attempt_number,
        )
        try:
            response = run_agent_process(
                task_id=task_id,
                role=role,
                model=model,
                label=f"{label_prefix}-{attempt_number}",
                prompt=current_prompt,
                worktree=worktree,
                run_dir=run_dir,
                timeout_seconds=timeout_seconds,
                settings=settings,
                paths=paths,
            )
            return response, attempts_remaining - offset
        except AgentProcessError as exc:
            last_error = exc
            if exc.status in {"cancelled", "timed_out"}:
                raise
            finding_example = (
                '[{"severity":"major","title":"Actionable issue",'
                '"detail":"Concrete impact and fix.","path":"runner.py","line":4}]'
                if role == "reviewer"
                else "[]"
            )
            current_prompt = (
                prompt
                + "\nRETRY_REQUIRED: The previous attempt did not return valid structured output or was interrupted. "
                "Do not repeat a plan. Complete the task, then return exactly this JSON shape with arrays where shown:\n"
                '{"schema_version":"career_local_dev_agent_response_v1","status":"completed",'
                '"summary":"concise result","details":[],"risks":[],"blocking_reason":null,'
                f'"findings":{finding_example},"requested_checks":[]}}\n'
                f"Previous coordinator error: {_redact_stream(str(exc))[:800]}\n"
            )
            if exc.status in {"cancelled", "timed_out"} and offset + 1 >= tries:
                raise
    if last_error:
        raise last_error
    raise AgentProcessError(f"Local {role} failed without a result.")


def _patch_result(response: AgentResponse, patch: PatchInfo) -> dict[str, Any]:
    return {
        **response.model_dump(mode="json"),
        "changed_files": list(patch.changed_files),
        "change_statuses": patch.statuses,
        "diff_lines": patch.diff_lines,
        "patch_sha256": patch.sha256,
    }


def _finish_run(
    task_id: str,
    *,
    status: str,
    phase: str,
    paths: CoordinatorPaths,
    error: str = "",
    **values: Any,
) -> dict[str, Any]:
    _update_run(
        task_id,
        db_path=paths.db_path,
        status=status,
        phase=phase,
        finished_at=utc_now_iso(),
        error=error,
        child_pid=None,
        **values,
    )
    run = get_run(task_id, db_path=paths.db_path)
    if run is None:
        raise CoordinatorError("Local-agent run disappeared.")
    return run
