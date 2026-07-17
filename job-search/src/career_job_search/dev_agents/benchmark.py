"""Qualification benchmark for local development-agent models."""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from career_job_search.dev_agents.common import (
    BENCHMARK_MODEL_TIMEOUT_SECONDS,
    AgentProcessError,
    CoordinatorError,
    CoordinatorPaths,
    SnapshotInfo,
    _json_dump,
    atomic_write_json,
    atomic_write_text,
    utc_now_iso,
)
from career_job_search.dev_agents.execution import (
    _ollama_model_identities,
    _run_with_process_retry,
    agent_response_search_text,
    build_agent_prompt,
    find_agent_policy_rejections,
    run_checks,
)
from career_job_search.dev_agents.models import (
    AgentTaskSpec,
    LocalAgentSettings,
    VerificationCheck,
)
from career_job_search.dev_agents.planner import resource_status
from career_job_search.dev_agents.review import evaluate_autonomy
from career_job_search.dev_agents.runs import connect, get_rollout, init_db
from career_job_search.dev_agents.snapshots import (
    _git,
    _git_bytes,
    _link_dependencies,
    _parse_tree_manifest,
    build_patch,
    cleanup_worktree,
    create_snapshot,
)


def _initialise_fixture(
    path: Path, *, include_review_target: bool = False
) -> tuple[str, str]:
    path.mkdir(parents=True, exist_ok=False)
    atomic_write_text(
        path / ".gitignore",
        ".venv\nnode_modules\n__pycache__/\n*.pyc\n",
        mode=0o644,
    )
    atomic_write_text(
        path / "calculator.py",
        '"""Tiny qualification fixture."""\n\n\ndef add(left: int, right: int) -> int:\n    return left - right\n',
        mode=0o644,
    )
    atomic_write_text(
        path / "test_calculator.py",
        "from calculator import add\n\n\ndef test_adds_two_numbers():\n    assert add(2, 3) == 5\n",
        mode=0o644,
    )
    atomic_write_text(
        path / "pytest.ini",
        "[pytest]\naddopts = -p no:cacheprovider\n",
        mode=0o644,
    )
    tracked_paths = [
        ".gitignore",
        "calculator.py",
        "test_calculator.py",
        "pytest.ini",
    ]
    if include_review_target:
        atomic_write_text(
            path / "runner.py",
            (
                '"""Safe review-fixture baseline."""\n\n'
                "def run(user_input: str):\n"
                "    return [user_input]\n"
            ),
            mode=0o644,
        )
        tracked_paths.append("runner.py")
    _git(["init", "-q"], cwd=path)
    _git(["add", *tracked_paths], cwd=path)
    commit_env = {
        "GIT_AUTHOR_NAME": "Career Local Agent",
        "GIT_AUTHOR_EMAIL": "local-agent@localhost",
        "GIT_COMMITTER_NAME": "Career Local Agent",
        "GIT_COMMITTER_EMAIL": "local-agent@localhost",
    }
    _git(
        ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
        cwd=path,
        env=commit_env,
    )
    commit = _git(["rev-parse", "HEAD"], cwd=path).stdout.strip()
    tree = _git(["rev-parse", "HEAD^{tree}"], cwd=path).stdout.strip()
    return commit, tree


def _initialise_implementation_fixture(
    path: Path, case_name: str
) -> tuple[str, str, str, str, str]:
    if case_name == "python":
        commit, tree = _initialise_fixture(path)
        return (
            commit,
            tree,
            "calculator.py",
            "test_calculator.py",
            "Fix calculator.add so the supplied test passes. Change only calculator.py and preserve the public function signature.",
        )
    path.mkdir(parents=True, exist_ok=False)
    atomic_write_text(
        path / ".gitignore",
        ".venv\nnode_modules\n__pycache__/\n*.pyc\n",
        mode=0o644,
    )
    atomic_write_text(
        path / "pytest.ini",
        "[pytest]\naddopts = -p no:cacheprovider\n",
        mode=0o644,
    )
    if case_name == "documentation":
        target = "GUIDE.md"
        test_file = "test_guide.py"
        objective = (
            "Correct GUIDE.md so it states exactly that local agents use Ollama only "
            "and cannot access the internet. Change only GUIDE.md."
        )
        atomic_write_text(
            path / target,
            "Local agents may access the internet when useful.\n",
            mode=0o644,
        )
        atomic_write_text(
            path / test_file,
            (
                "from pathlib import Path\n\n\n"
                "def test_local_only_statement():\n"
                "    assert Path('GUIDE.md').read_text() == "
                "'Local agents use Ollama only and cannot access the internet.\\n'\n"
            ),
            mode=0o644,
        )
    elif case_name == "dashboard":
        target = "status.ts"
        test_file = "test_status.py"
        objective = (
            "Fix only the misspelled running status value in status.ts. Preserve the "
            "export name and change no other file."
        )
        atomic_write_text(
            path / target,
            "export const statusLabel = 'runnng'\n",
            mode=0o644,
        )
        atomic_write_text(
            path / test_file,
            (
                "from pathlib import Path\n\n\n"
                "def test_running_status_spelling():\n"
                "    text = Path('status.ts').read_text()\n"
                "    assert \"statusLabel = 'running'\" in text\n"
                "    assert 'runnng' not in text\n"
            ),
            mode=0o644,
        )
    else:
        raise CoordinatorError(f"Unknown qualification fixture: {case_name}")
    _git(["init", "-q"], cwd=path)
    _git(["add", ".gitignore", "pytest.ini", target, test_file], cwd=path)
    _git(
        ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
        cwd=path,
        env={
            "GIT_AUTHOR_NAME": "Career Local Agent",
            "GIT_AUTHOR_EMAIL": "local-agent@localhost",
            "GIT_COMMITTER_NAME": "Career Local Agent",
            "GIT_COMMITTER_EMAIL": "local-agent@localhost",
        },
    )
    commit = _git(["rev-parse", "HEAD"], cwd=path).stdout.strip()
    tree = _git(["rev-parse", "HEAD^{tree}"], cwd=path).stdout.strip()
    return commit, tree, target, test_file, objective


def _benchmark_implementer_case(
    model: str,
    case_name: str,
    *,
    benchmark_root: Path,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
) -> dict[str, Any]:
    started = time.monotonic()
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", model)
    fixture = benchmark_root / f"implementer-{slug}-{case_name}"
    commit, tree, target, test_file, objective = _initialise_implementation_fixture(
        fixture, case_name
    )
    _link_dependencies(fixture, paths.repo_root)
    run_dir = benchmark_root / f"implementer-run-{slug}-{case_name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = _parse_tree_manifest(
        _git_bytes(["ls-tree", "-r", "-z", "--full-tree", commit], cwd=fixture)
    )
    manifest_path = run_dir / "snapshot-manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema": "career_local_dev_snapshot_v1",
            "commit": commit,
            "tree": tree,
            "files": manifest,
        },
    )
    snapshot = SnapshotInfo(
        commit=commit,
        tree=tree,
        worktree=fixture,
        manifest_path=manifest_path,
        excluded_paths=(),
    )
    task = AgentTaskSpec(
        objective=objective,
        role="implementer",
        allowed_paths=[target],
        acceptance_checks=[
            VerificationCheck(
                name="qualification pytest",
                argv=[
                    "python",
                    "-m",
                    "pytest",
                    "-q",
                    "-c",
                    "pytest.ini",
                    "--rootdir",
                    ".",
                    test_file,
                ],
            )
        ],
        max_changed_files=1,
        max_diff_lines=20,
        timeout_seconds=BENCHMARK_MODEL_TIMEOUT_SECONDS,
        context_notes=(
            "Qualification fixture: make the exact small edit, inspect the diff, "
            "and return the required JSON immediately. Do not run tests, search for "
            "packages, or install anything; the coordinator runs the supplied check."
        ),
    )
    task_id = f"agent_{uuid4().hex}"
    response, _ = _run_with_process_retry(
        task_id=task_id,
        role="implementer",
        model=model,
        label_prefix="qualification-implementer",
        prompt=build_agent_prompt(task, role="implementer"),
        worktree=fixture,
        run_dir=run_dir,
        timeout_seconds=BENCHMARK_MODEL_TIMEOUT_SECONDS,
        settings=settings,
        paths=paths,
        attempts_remaining=settings.limits.retry_count,
    )
    policy_rejections = find_agent_policy_rejections(run_dir)
    patch = build_patch(task, snapshot, settings=settings, run_dir=run_dir)
    checks = run_checks(
        task.acceptance_checks,
        worktree=fixture,
        run_dir=run_dir / "checks",
        task_id=task_id,
        settings=settings,
        paths=paths,
    )
    passed = (
        response.status == "completed"
        and not policy_rejections
        and patch.changed_files == (target,)
        and bool(checks)
        and all(item.status == "passed" for item in checks)
    )
    return {
        "passed": passed,
        "case": case_name,
        "model": model,
        "model_digest": settings.models[model].digest,
        "duration_seconds": round(time.monotonic() - started, 3),
        "summary": response.summary,
        "changed_files": list(patch.changed_files),
        "checks": [item.model_dump(mode="json") for item in checks],
        "policy_rejections": policy_rejections,
    }


def _benchmark_implementer(
    model: str,
    *,
    benchmark_root: Path,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
) -> dict[str, Any]:
    started = time.monotonic()
    cases: list[dict[str, Any]] = []
    for case_name in ("python", "documentation", "dashboard"):
        try:
            result = _benchmark_implementer_case(
                model,
                case_name,
                benchmark_root=benchmark_root,
                settings=settings,
                paths=paths,
            )
        except (CoordinatorError, AgentProcessError, OSError) as exc:
            result = {
                "passed": False,
                "case": case_name,
                "model": model,
                "model_digest": settings.models[model].digest,
                "error": str(exc),
            }
        cases.append(result)
        if not result.get("passed"):
            break
    return {
        "passed": len(cases) == 3 and all(case.get("passed") for case in cases),
        "model": model,
        "model_digest": settings.models[model].digest,
        "duration_seconds": round(time.monotonic() - started, 3),
        "cases": cases,
        "summary": "; ".join(
            str(case.get("summary") or case.get("error") or case["case"])
            for case in cases
        )[:2000],
    }


def benchmark(
    *,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
    candidate_model: str | None = None,
) -> dict[str, Any]:
    """Qualify and compare a pinned implementer candidate before promotion."""

    init_db(paths.db_path, settings=settings)
    resources = resource_status("implementer", settings=settings, paths=paths)
    if not resources["ok"]:
        raise CoordinatorError(f"Model benchmark deferred: {resources['reason']}")
    candidate = candidate_model or settings.implementer_candidates[0]
    if candidate not in settings.implementer_candidates:
        raise CoordinatorError("Candidate model is not in the configured allowlist.")
    identities = _ollama_model_identities(settings)
    for model in {candidate, settings.implementer_fallback}:
        expected = settings.models[model].digest
        if identities.get(model) != expected:
            raise CoordinatorError(
                f"Model {model} is missing or its digest changed; update configuration before qualification."
            )
    current_rollout = get_rollout(settings=settings, db_path=paths.db_path)
    previous_selected = current_rollout.get("selected_implementer_model")
    benchmark_root = (
        paths.runtime_root
        / "benchmarks"
        / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    )
    benchmark_root.mkdir(parents=True, exist_ok=False)
    results: dict[str, Any] = {}
    explorer_snapshot: SnapshotInfo | None = None
    try:
        explorer_id = f"agent_{uuid4().hex}"
        explorer_run_dir = paths.runtime_root / "runs" / explorer_id
        explorer_run_dir.mkdir(parents=True, exist_ok=False)
        explorer_snapshot = create_snapshot(explorer_id, settings=settings, paths=paths)
        explorer_task = AgentTaskSpec(
            objective=(
                "Inspect this repository read-only. Run only these two short commands: "
                "`sed -n '1,20p' README.md` and "
                "`find tools dashboard tests -maxdepth 1 -type f | sort | head -30`. "
                "Then summarise the purpose of the tools, dashboard, and tests "
                "directories in exactly three concise details."
            ),
            role="explorer",
            allowed_paths=["."],
            context_notes=(
                "Qualification: use at most three short read commands. Do not run "
                "ls -R. Inspect only a few representative files, then return exactly "
                "three details."
            ),
            timeout_seconds=BENCHMARK_MODEL_TIMEOUT_SECONDS,
        )
        explorer_response, _ = _run_with_process_retry(
            task_id=explorer_id,
            role="explorer",
            model=settings.roles["explorer"].model,
            label_prefix="qualification-explorer",
            prompt=build_agent_prompt(explorer_task, role="explorer"),
            worktree=explorer_snapshot.worktree,
            run_dir=explorer_run_dir,
            timeout_seconds=BENCHMARK_MODEL_TIMEOUT_SECONDS,
            settings=settings,
            paths=paths,
            attempts_remaining=settings.limits.retry_count,
        )
        explorer_policy_rejections = find_agent_policy_rejections(explorer_run_dir)
        exploration_text = agent_response_search_text(explorer_response)
        results["explorer"] = {
            "passed": explorer_response.status == "completed"
            and not explorer_policy_rejections
            and all(
                name in exploration_text for name in ("tools", "dashboard", "tests")
            ),
            "model": settings.roles["explorer"].model,
            "summary": explorer_response.summary,
            "policy_rejections": explorer_policy_rejections,
        }
    except (CoordinatorError, AgentProcessError) as exc:
        results["explorer"] = {
            "passed": False,
            "model": settings.roles["explorer"].model,
            "error": str(exc),
        }
    finally:
        if explorer_snapshot and explorer_snapshot.worktree.exists():
            cleanup_worktree(explorer_snapshot.worktree, paths=paths, force=True)

    selected: str | None = None
    implementer_attempts: list[dict[str, Any]] = []
    for model in (candidate, settings.implementer_fallback):
        if any(item.get("model") == model for item in implementer_attempts):
            continue
        try:
            attempt = _benchmark_implementer(
                model,
                benchmark_root=benchmark_root,
                settings=settings,
                paths=paths,
            )
        except (CoordinatorError, AgentProcessError, OSError) as exc:
            attempt = {
                "passed": False,
                "model": model,
                "model_digest": settings.models[model].digest,
                "error": str(exc),
            }
        implementer_attempts.append(attempt)
    candidate_attempt = next(
        (item for item in implementer_attempts if item.get("model") == candidate),
        None,
    )
    fallback_attempt = next(
        (
            item
            for item in implementer_attempts
            if item.get("model") == settings.implementer_fallback
        ),
        None,
    )
    candidate_wins = bool(candidate_attempt and candidate_attempt.get("passed"))
    if (
        candidate_wins
        and fallback_attempt
        and fallback_attempt.get("passed")
        and float(candidate_attempt.get("duration_seconds") or 0)
        > 1.5 * max(float(fallback_attempt.get("duration_seconds") or 0), 0.001)
    ):
        candidate_wins = False
    if candidate_wins:
        selected = candidate
    elif fallback_attempt and fallback_attempt.get("passed"):
        selected = settings.implementer_fallback
    results["implementer"] = {
        "passed": bool(selected),
        "candidate_model": candidate,
        "candidate_wins": candidate_wins,
        "selected_model": selected,
        "attempts": implementer_attempts,
    }

    reviewer_model = settings.roles["reviewer"].model
    reviewer_dir = benchmark_root / "reviewer"
    _initialise_fixture(reviewer_dir, include_review_target=True)
    reviewer_task = AgentTaskSpec(
        objective=(
            "Review the supplied patch. It passes untrusted user input to a shell "
            "and must be reported as an actionable major or critical finding."
        ),
        role="reviewer",
        allowed_paths=["runner.py"],
        timeout_seconds=settings.roles["reviewer"].timeout_seconds,
    )
    seeded_patch = """diff --git a/runner.py b/runner.py
--- a/runner.py
+++ b/runner.py
@@ -1,3 +1,4 @@
 import subprocess
 def run(user_input: str):
-    return [user_input]
+    return subprocess.run(user_input, shell=True)
"""
    try:
        reviewer_response, _ = _run_with_process_retry(
            task_id=f"agent_{uuid4().hex}",
            role="reviewer",
            model=reviewer_model,
            label_prefix="qualification-reviewer",
            prompt=build_agent_prompt(
                reviewer_task, role="reviewer", patch=seeded_patch
            ),
            worktree=reviewer_dir,
            run_dir=benchmark_root / "reviewer-run",
            timeout_seconds=BENCHMARK_MODEL_TIMEOUT_SECONDS,
            settings=settings,
            paths=paths,
            attempts_remaining=settings.limits.retry_count,
        )
        reviewer_policy_rejections = find_agent_policy_rejections(
            benchmark_root / "reviewer-run"
        )
        blocking = [
            finding
            for finding in reviewer_response.findings
            if finding.severity in {"critical", "major"}
        ]
        results["reviewer"] = {
            "passed": reviewer_response.status == "completed"
            and bool(blocking)
            and not reviewer_policy_rejections,
            "model": reviewer_model,
            "summary": reviewer_response.summary,
            "findings": [item.model_dump(mode="json") for item in blocking],
            "policy_rejections": reviewer_policy_rejections,
        }
    except (CoordinatorError, AgentProcessError) as exc:
        results["reviewer"] = {
            "passed": False,
            "model": reviewer_model,
            "error": str(exc),
        }

    qualified = bool(
        results.get("explorer", {}).get("passed")
        and results.get("implementer", {}).get("passed")
        and results.get("reviewer", {}).get("passed")
        and selected
    )
    now = utc_now_iso()
    payload = {
        "schema": "career_local_dev_agent_qualification_v2",
        "qualified": qualified,
        "qualified_at": now if qualified else None,
        "candidate_model": candidate,
        "previous_selected_model": previous_selected,
        "selected_model": selected if qualified else previous_selected,
        "promoted": bool(
            qualified and selected == candidate and selected != previous_selected
        ),
        "resource_status": resources,
        "results": results,
        "artifact_root": str(benchmark_root),
    }
    with connect(paths.db_path) as con:
        shared_roles_passed = bool(
            results.get("explorer", {}).get("passed")
            and results.get("reviewer", {}).get("passed")
        )
        for attempt in implementer_attempts:
            model = str(attempt["model"])
            digest = settings.models[model].digest
            model_qualified = bool(shared_roles_passed and attempt.get("passed"))
            model_payload = {
                **payload,
                "qualified": model_qualified,
                "qualified_model": model,
            }
            con.execute(
                """
                INSERT INTO local_agent_model_qualifications(
                  model_tag, model_digest, qualified, qualified_at,
                  qualification_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_tag, model_digest) DO UPDATE SET
                  qualified = excluded.qualified,
                  qualified_at = excluded.qualified_at,
                  qualification_json = excluded.qualification_json,
                  updated_at = excluded.updated_at
                """,
                (
                    model,
                    digest,
                    1 if model_qualified else 0,
                    now if model_qualified else None,
                    _json_dump(model_payload),
                    now,
                ),
            )
        if qualified and selected:
            selected_digest = settings.models[selected].digest
            con.execute(
                """
                UPDATE local_agent_settings
                SET qualified_at = ?, selected_implementer_model = ?,
                    selected_implementer_digest = ?, qualification_json = ?,
                    safe_applied_runs = COALESCE((
                      SELECT safe_applied_runs
                      FROM local_agent_model_qualifications
                      WHERE model_tag = ? AND model_digest = ?
                    ), 0),
                    updated_at = ?
                WHERE id = 1
                """,
                (
                    now,
                    selected,
                    selected_digest,
                    _json_dump(payload),
                    selected,
                    selected_digest,
                    now,
                ),
            )
    evaluate_autonomy(settings=settings, paths=paths)
    return payload
