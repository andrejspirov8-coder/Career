from __future__ import annotations

import json
import platform
import shutil
import signal
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

import local_dev_agents as agents
from local_dev_agent_models import (
    AgentResponse,
    AgentTaskSpec,
    PlannerProposalDraft,
    VerificationCheck,
)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def local_repo(tmp_path: Path) -> tuple[agents.CoordinatorPaths, agents.LocalAgentSettings]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tools").mkdir()
    (repo / "tests").mkdir()
    (repo / ".gitignore").write_text(
        ".env*\nstate/\nruntime/\n.venv/\nnode_modules/\n*.pdf\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("original\n", encoding="utf-8")
    (repo / "tools" / "example.py").write_text("VALUE = 1\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "add", ".")
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            "initial",
        ],
        cwd=repo,
        check=True,
    )
    runtime = repo / "runtime" / "local-dev-agents"
    paths = agents.CoordinatorPaths(
        repo_root=repo,
        runtime_root=runtime,
        db_path=runtime / "agent_runs.sqlite3",
        worktree_root=tmp_path / "worktrees",
        backup_root=tmp_path / "backups",
        config_path=agents.DEFAULT_CONFIG_PATH,
    )
    return paths, agents.load_settings()


def task(**updates: object) -> AgentTaskSpec:
    payload: dict[str, object] = {
        "objective": "Update the bounded example implementation and keep tests passing.",
        "role": "implementer",
        "allowed_paths": ["tools/example.py"],
        "max_changed_files": 1,
        "max_diff_lines": 20,
    }
    payload.update(updates)
    return AgentTaskSpec.model_validate(payload)


def prepare_patch_run(
    paths: agents.CoordinatorPaths,
    settings: agents.LocalAgentSettings,
    *,
    new_content: str = "VALUE = 2\n",
) -> tuple[dict[str, object], agents.SnapshotInfo, agents.PatchInfo]:
    created = agents.create_run(task(), settings=settings, paths=paths)
    task_id = str(created["task_id"])
    agents._update_run(
        task_id,
        db_path=paths.db_path,
        status="snapshotting",
        phase="snapshotting",
        started_at=agents.utc_now_iso(),
    )
    snapshot = agents.create_snapshot(task_id, settings=settings, paths=paths)
    (snapshot.worktree / "tools" / "example.py").write_text(
        new_content, encoding="utf-8"
    )
    cache_dir = snapshot.worktree / "tools" / "__pycache__"
    cache_dir.mkdir(exist_ok=True)
    (cache_dir / "example.pyc").write_bytes(b"generated cache")
    run_dir = paths.runtime_root / "runs" / task_id
    patch = agents.build_patch(
        task(), snapshot, settings=settings, run_dir=run_dir
    )
    assert patch.changed_files == ("tools/example.py",)
    result = {
        "status": "completed",
        "summary": "Updated example.",
        "changed_files": list(patch.changed_files),
        "change_statuses": patch.statuses,
        "diff_lines": patch.diff_lines,
        "patch_sha256": patch.sha256,
    }
    agents._update_run(
        task_id,
        db_path=paths.db_path,
        status="ready_for_codex_review",
        phase="ready_for_codex_review",
        snapshot_commit=snapshot.commit,
        worktree_path=str(snapshot.worktree),
        patch_path=str(patch.path),
        patch_sha256=patch.sha256,
        result_json=json.dumps(result),
        verification_json="[]",
    )
    prepared = agents.get_run(task_id, db_path=paths.db_path)
    assert prepared is not None
    return prepared, snapshot, patch


def test_task_contract_rejects_unbounded_implementer() -> None:
    with pytest.raises(ValidationError, match="bounded paths"):
        task(allowed_paths=["."])


def test_settings_reject_nonlocal_ollama_endpoint() -> None:
    payload = agents.load_settings().model_dump(mode="json")
    payload["ollama_host"] = "https://example.com"
    with pytest.raises(ValidationError, match="fixed local-only endpoint"):
        agents.LocalAgentSettings.model_validate(payload)


def test_settings_match_running_ollama_context_limit() -> None:
    settings = agents.load_settings()
    assert settings.models["gpt-oss:20b"].context_window == 32768
    assert settings.models["gpt-oss:20b"].use_cli_output_schema is False
    assert (
        settings.models["qwen3.5:35b-a3b-coding-nvfp4"].context_window
        == 32768
    )
    assert (
        settings.models["qwen3.5:35b-a3b-coding-nvfp4"].use_cli_output_schema
        is True
    )
    assert "qwen3.6:35b-a3b-coding-nvfp4" in settings.implementer_candidates
    assert len(settings.models["qwen3.6:35b-a3b-coding-nvfp4"].digest) == 64


def _store_test_proposal(
    paths: agents.CoordinatorPaths,
    settings: agents.LocalAgentSettings,
    *,
    objective: str,
    category: str = "tests",
    allowed_path: str = "tests/test_generated.py",
) -> dict[str, object]:
    planner_task = agents.create_run(
        task(
            objective="Inspect the bounded test surface and propose one safe task.",
            role="planner",
            allowed_paths=["tests"],
        ),
        settings=settings,
        paths=paths,
    )
    planner_run_id = f"planner_{agents.uuid4().hex}"
    with agents.connect(paths.db_path) as con:
        con.execute(
            """
            INSERT INTO local_agent_planner_runs(
              planner_run_id, task_id, trigger_source, status, model,
              model_digest, started_at
            ) VALUES (?, ?, 'manual', 'completed', ?, ?, ?)
            """,
            (
                planner_run_id,
                planner_task["task_id"],
                settings.roles["planner"].model,
                settings.models[settings.roles["planner"].model].digest,
                agents.utc_now_iso(),
            ),
        )
    stored = agents.store_planner_proposals(
        planner_run_id,
        [
            PlannerProposalDraft(
                objective=objective,
                category=category,
                evidence=[f"{allowed_path}: deterministic test gap"],
                allowed_paths=[allowed_path],
                check_preset="python",
                risk="low",
                priority="medium",
                estimated_files=1,
                estimated_diff_lines=80,
            )
        ],
        settings=settings,
        paths=paths,
    )
    assert len(stored) == 1
    return stored[0]


def test_planner_proposals_are_deduplicated_and_require_user_approval(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
) -> None:
    paths, settings = local_repo
    proposal = _store_test_proposal(
        paths,
        settings,
        objective="Add a focused regression test for the generated fixture behavior.",
    )

    approved = agents.approve_proposal(
        str(proposal["proposal_id"]), settings=settings, paths=paths
    )

    assert approved["proposal"]["status"] == "queued"
    assert approved["run"]["proposal_id"] == proposal["proposal_id"]
    assert approved["run"]["role"] == "implementer"
    assert approved["run"]["task"]["acceptance_checks"][0]["argv"] == [
        "python",
        "-m",
        "pytest",
        "-q",
    ]


def test_planner_daily_approval_cap_is_two(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
) -> None:
    paths, settings = local_repo
    proposals = [
        _store_test_proposal(
            paths,
            settings,
            objective=f"Add focused regression coverage for safe fixture case number {index}.",
            allowed_path=f"tests/test_generated_{index}.py",
        )
        for index in range(3)
    ]
    agents.approve_proposal(
        str(proposals[0]["proposal_id"]), settings=settings, paths=paths
    )
    agents.approve_proposal(
        str(proposals[1]["proposal_id"]), settings=settings, paths=paths
    )

    with pytest.raises(agents.CoordinatorError, match="daily limit"):
        agents.approve_proposal(
            str(proposals[2]["proposal_id"]), settings=settings, paths=paths
        )


def test_concurrent_proposal_approval_creates_only_one_run(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
) -> None:
    paths, settings = local_repo
    proposal = _store_test_proposal(
        paths,
        settings,
        objective="Add one focused regression test for concurrent approval behavior.",
    )
    proposal_id = str(proposal["proposal_id"])
    barrier = threading.Barrier(2)
    results: list[dict[str, object]] = []
    errors: list[Exception] = []

    def approve() -> None:
        barrier.wait()
        try:
            results.append(
                agents.approve_proposal(
                    proposal_id, settings=settings, paths=paths
                )
            )
        except Exception as exc:  # noqa: BLE001 - assert concurrent outcome below
            errors.append(exc)

    workers = [threading.Thread(target=approve) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], agents.CoordinatorError)
    with agents.connect(paths.db_path) as con:
        count = con.execute(
            "SELECT COUNT(*) FROM local_agent_runs WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()[0]
    assert count == 1


def test_model_digest_change_blocks_local_writing(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, settings = local_repo
    agents.init_db(paths.db_path, settings=settings)
    model = "qwen3.5:35b-a3b-coding-nvfp4"
    digest = settings.models[model].digest
    with agents.connect(paths.db_path) as con:
        con.execute(
            """
            UPDATE local_agent_settings
            SET qualified_at = ?, selected_implementer_model = ?,
                selected_implementer_digest = ? WHERE id = 1
            """,
            (agents.utc_now_iso(), model, digest),
        )
        con.execute(
            """
            INSERT INTO local_agent_model_qualifications(
              model_tag, model_digest, qualified, qualified_at, updated_at
            ) VALUES (?, ?, 1, ?, ?)
            """,
            (model, digest, agents.utc_now_iso(), agents.utc_now_iso()),
        )
    monkeypatch.setattr(
        agents,
        "_ollama_model_identities",
        lambda _settings: {
            "qwen3.5:35b-a3b-coding-nvfp4": "0" * 64,
        },
    )

    with pytest.raises(agents.CoordinatorError, match="changed or is unavailable"):
        agents._selected_implementer_identity(settings=settings, paths=paths)


def test_model_benchmark_defers_when_implementation_resources_are_busy(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, settings = local_repo
    monkeypatch.setattr(
        agents,
        "resource_status",
        lambda *_args, **_kwargs: {
            "ok": False,
            "reason": "the release verification gate is currently running",
            "facts": {},
        },
    )

    with pytest.raises(agents.CoordinatorError, match="benchmark deferred"):
        agents.benchmark(settings=settings, paths=paths)


def test_timeout_does_not_consume_a_second_full_model_attempt(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, settings = local_repo
    created = agents.create_run(
        task(role="explorer", allowed_paths=["."]),
        settings=settings,
        paths=paths,
    )
    attempts = 0

    def time_out(**_kwargs: object) -> AgentResponse:
        nonlocal attempts
        attempts += 1
        raise agents.AgentProcessError("timed out", status="timed_out")

    monkeypatch.setattr(agents, "run_agent_process", time_out)
    with pytest.raises(agents.AgentProcessError, match="timed out"):
        agents._run_with_process_retry(
            task_id=str(created["task_id"]),
            role="explorer",
            model=settings.roles["explorer"].model,
            label_prefix="test",
            prompt="{}",
            worktree=paths.repo_root,
            run_dir=paths.runtime_root / "runs" / str(created["task_id"]),
            timeout_seconds=1,
            settings=settings,
            paths=paths,
            attempts_remaining=1,
        )
    assert attempts == 1


def test_weekday_planner_schedule_catches_up_once(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
) -> None:
    paths, settings = local_repo
    now = datetime(2026, 7, 20, 18, 30, tzinfo=UTC)  # 21:30 in Vilnius, Monday

    due = agents._planner_schedule_due(now, settings=settings, paths=paths)

    assert due == ("2026-07-20", "schedule_catch_up")
    planner_task = agents.create_run(
        task(
            objective="Inspect the bounded tests and propose a safe local task.",
            role="planner",
            allowed_paths=["tests"],
        ),
        settings=settings,
        paths=paths,
    )
    with agents.connect(paths.db_path) as con:
        con.execute(
            """
            INSERT INTO local_agent_planner_runs(
              planner_run_id, task_id, trigger_source, scheduled_for, status,
              model, model_digest, started_at
            ) VALUES (?, ?, 'schedule_catch_up', '2026-07-20', 'completed', ?, ?, ?)
            """,
            (
                f"planner_{'a' * 32}",
                planner_task["task_id"],
                settings.roles["planner"].model,
                settings.models[settings.roles["planner"].model].digest,
                agents.utc_now_iso(),
            ),
        )
    assert agents._planner_schedule_due(now, settings=settings, paths=paths) is None


def test_autonomy_reaches_tier_two_only_for_pinned_safe_history(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
) -> None:
    paths, settings = local_repo
    agents.init_db(paths.db_path, settings=settings)
    model = "qwen3.5:35b-a3b-coding-nvfp4"
    digest = settings.models[model].digest
    now = agents.utc_now_iso()
    with agents.connect(paths.db_path) as con:
        con.execute(
            """
            UPDATE local_agent_settings
            SET qualified_at = ?, selected_implementer_model = ?,
                selected_implementer_digest = ? WHERE id = 1
            """,
            (now, model, digest),
        )
        con.execute(
            """
            INSERT INTO local_agent_model_qualifications(
              model_tag, model_digest, qualified, qualified_at,
              safe_applied_runs, safe_apply_streak, total_applied_runs,
              first_pass_applied_runs, updated_at
            ) VALUES (?, ?, 1, ?, 20, 20, 20, 20, ?)
            """,
            (model, digest, now, now),
        )
        for index in range(20):
            con.execute(
                """
                INSERT INTO local_agent_runs(
                  task_id, status, phase, role, model, model_digest, task_json,
                  created_at, finished_at, run_dir, first_pass_ok, error
                ) VALUES (?, 'applied', 'applied', 'implementer', ?, ?, ?, ?, ?, ?, 1, '')
                """,
                (
                    f"agent_{index:032x}",
                    model,
                    digest,
                    task().model_dump_json(),
                    now,
                    now,
                    str(paths.runtime_root / "runs" / f"agent_{index:032x}"),
                ),
            )

    autonomy = agents.evaluate_autonomy(settings=settings, paths=paths)

    assert autonomy["tier"] == 2
    assert autonomy["auto_apply_enabled"] is True
    assert autonomy["rolling_first_pass_rate"] == 1.0


def test_auto_apply_allowlist_is_limited_to_documentation_and_tests() -> None:
    assert agents._is_auto_apply_path("documentation", "docs/guide.md")
    assert not agents._is_auto_apply_path("documentation", "README.md")
    assert agents._is_auto_apply_path("tests", "tests/test_feature.py")
    assert agents._is_auto_apply_path(
        "tests", "dashboard/lib/feature.test.ts"
    )
    assert agents._is_auto_apply_path(
        "tests", "raycast-job-search-hub/src/__tests__/feature.test.ts"
    )
    assert not agents._is_auto_apply_path("tests", "tools/feature.py")


def test_plain_text_findings_are_nonblocking_structured_notes() -> None:
    response = AgentResponse.model_validate(
        {
            "status": "completed",
            "summary": "Completed fixture.",
            "findings": ["The original function subtracted the values."],
        }
    )
    assert len(response.findings) == 1
    assert response.findings[0].severity == "note"
    assert response.findings[0].detail.startswith("The original function")


def test_implementer_prompt_uses_supported_local_edit_route() -> None:
    prompt = agents.build_agent_prompt(task(), role="implementer")
    assert "does not provide apply_patch" in prompt
    assert "Never call apply_patch" in prompt


def test_reviewer_prompt_requires_structured_blocker_findings() -> None:
    prompt = agents.build_agent_prompt(
        task(role="reviewer", allowed_paths=["runner.py"]),
        role="reviewer",
        patch="diff --git a/runner.py b/runner.py\n",
    )
    instructions = json.loads(prompt)["instructions"]
    assert any('"severity":"major"' in item for item in instructions)
    assert any("never as strings" in item for item in instructions)


def test_policy_routes_sensitive_and_dependency_work_to_main_codex() -> None:
    settings = agents.load_settings()
    with pytest.raises(agents.CoordinatorError, match="Sensitive"):
        agents.validate_task_policy(
            task(objective="Change authentication token handling safely."),
            settings=settings,
        )
    with pytest.raises(agents.CoordinatorError, match="protected path"):
        agents.validate_task_policy(
            task(allowed_paths=["pyproject.toml"]), settings=settings
        )


def test_check_contract_allows_only_shell_free_test_commands() -> None:
    agents.validate_check(
        VerificationCheck(
            name="pytest",
            argv=["python", "-m", "pytest", "-q", "tests/test_one.py"],
        )
    )
    agents.validate_check(
        VerificationCheck(name="typecheck", argv=["npm", "run", "typecheck"])
    )
    with pytest.raises(agents.CoordinatorError, match="unsupported npm"):
        agents.validate_check(
            VerificationCheck(name="install", argv=["npm", "install"])
        )
    with pytest.raises(agents.CoordinatorError, match="unsupported executable"):
        agents.validate_check(
            VerificationCheck(name="shell", argv=["bash", "-lc", "true"])
        )


def test_safe_environment_does_not_inherit_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VERY_SECRET_TOKEN", "do-not-leak")
    monkeypatch.setenv("PATH", "/private/user-controlled-bin")
    environment = agents.safe_agent_environment(
        home=tmp_path / "home",
        codex_home=tmp_path / "codex",
        temp_dir=tmp_path / "tmp",
        settings=agents.load_settings(),
    )
    assert "VERY_SECRET_TOKEN" not in environment
    assert "/private/user-controlled-bin" not in environment["PATH"]
    assert set(environment) == {
        "PATH",
        "HOME",
        "CODEX_HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "OLLAMA_HOST",
        "GIT_OPTIONAL_LOCKS",
        "NO_COLOR",
        "CI",
        "NEXT_TELEMETRY_DISABLED",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "PYTHONNOUSERSITE",
    }
    assert environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert environment["PYTHONNOUSERSITE"] == "1"


def test_qualification_fixture_has_local_pytest_boundary(tmp_path: Path) -> None:
    fixture = tmp_path / "qualification"
    agents._initialise_fixture(fixture)
    assert (fixture / "pytest.ini").read_text(encoding="utf-8").startswith(
        "[pytest]"
    )
    tracked = git(fixture, "ls-files").splitlines()
    assert "pytest.ini" in tracked
    assert ".gitignore" in tracked
    (fixture / "__pycache__").mkdir()
    (fixture / "__pycache__" / "calculator.pyc").write_bytes(b"generated")
    assert git(fixture, "status", "--short") == ""


def test_forbidden_agent_command_is_detected_from_process_log(tmp_path: Path) -> None:
    attempt = tmp_path / "implementer-1"
    attempt.mkdir()
    (attempt / "stderr.log").write_text(
        "Rejected: Dependency installation is disabled; use the locked environment.\n",
        encoding="utf-8",
    )

    rejections = agents.find_agent_policy_rejections(tmp_path)

    assert len(rejections) == 1
    assert "Dependency installation is disabled" in rejections[0]


def test_single_fenced_json_response_is_strictly_validated(tmp_path: Path) -> None:
    response_path = tmp_path / "response.json"
    payload = AgentResponse(
        status="completed",
        summary="Completed the bounded fixture.",
    ).model_dump_json()
    response_path.write_text(f"```json\n{payload}\n```\n", encoding="utf-8")

    response = agents.load_structured_response(response_path, AgentResponse)

    assert response.status == "completed"
    assert response.summary == "Completed the bounded fixture."


def test_fenced_json_with_extra_prose_is_rejected(tmp_path: Path) -> None:
    response_path = tmp_path / "response.json"
    response_path.write_text(
        "Here is the result:\n```json\n{}\n```\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        agents.load_structured_response(response_path, AgentResponse)


def test_qualification_searches_normalised_finding_notes() -> None:
    response = AgentResponse(
        status="completed",
        summary="Read the requested files.",
        findings=[
            "Tools contain helpers; dashboard contains the web app; tests validate both."
        ],
    )

    text = agents.agent_response_search_text(response)

    assert all(name in text for name in ("tools", "dashboard", "tests"))


def test_snapshot_captures_dirty_and_untracked_without_touching_active_index(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
) -> None:
    paths, settings = local_repo
    (paths.repo_root / "README.md").write_text("dirty\n", encoding="utf-8")
    (paths.repo_root / "notes.txt").write_text("untracked\n", encoding="utf-8")
    (paths.repo_root / ".env.local").write_text("SECRET=yes\n", encoding="utf-8")
    (paths.repo_root / "state").mkdir()
    (paths.repo_root / "state" / "private.json").write_text("{}\n", encoding="utf-8")
    (paths.repo_root / "credentials.json").write_text("{}\n", encoding="utf-8")
    (paths.repo_root / "fixture.sqlite3").write_text("private\n", encoding="utf-8")
    (paths.repo_root / "browser-profile").mkdir()
    (paths.repo_root / "browser-profile" / "session.json").write_text("{}\n", encoding="utf-8")
    before_status = git(paths.repo_root, "status", "--porcelain=v2")
    before_head = git(paths.repo_root, "rev-parse", "HEAD")
    created = agents.create_run(
        task(role="explorer", allowed_paths=["."]),
        settings=settings,
        paths=paths,
    )

    snapshot = agents.create_snapshot(
        str(created["task_id"]), settings=settings, paths=paths
    )

    assert (snapshot.worktree / "README.md").read_text() == "dirty\n"
    assert (snapshot.worktree / "notes.txt").read_text() == "untracked\n"
    assert git(snapshot.worktree, "rev-list", "--count", "--all") == "1"
    assert not (snapshot.worktree / ".env.local").exists()
    assert not (snapshot.worktree / "state").exists()
    assert not (snapshot.worktree / "credentials.json").exists()
    assert not (snapshot.worktree / "fixture.sqlite3").exists()
    assert not (snapshot.worktree / "browser-profile").exists()
    assert git(paths.repo_root, "status", "--porcelain=v2") == before_status
    assert git(paths.repo_root, "rev-parse", "HEAD") == before_head
    agents.cleanup_worktree(snapshot.worktree, paths=paths, force=True)


def test_snapshot_rejects_symlink_outside_repository(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
    tmp_path: Path,
) -> None:
    paths, settings = local_repo
    outside = tmp_path / "outside.txt"
    outside.write_text("private\n", encoding="utf-8")
    (paths.repo_root / "outside-link").symlink_to(outside)
    created = agents.create_run(
        task(role="explorer", allowed_paths=["."]),
        settings=settings,
        paths=paths,
    )
    with pytest.raises(agents.CoordinatorError, match="leaves the repository"):
        agents.create_snapshot(
            str(created["task_id"]), settings=settings, paths=paths
        )


def test_patch_rejects_out_of_scope_and_deletions(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
) -> None:
    paths, settings = local_repo
    created = agents.create_run(task(), settings=settings, paths=paths)
    snapshot = agents.create_snapshot(
        str(created["task_id"]), settings=settings, paths=paths
    )
    (snapshot.worktree / "README.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(agents.CoordinatorError, match="out-of-scope"):
        agents.build_patch(
            task(),
            snapshot,
            settings=settings,
            run_dir=paths.runtime_root / "runs" / str(created["task_id"]),
        )

    (snapshot.worktree / "README.md").write_text("original\n", encoding="utf-8")
    (snapshot.worktree / "tools" / "example.py").unlink()
    with pytest.raises(agents.CoordinatorError, match="may not delete"):
        agents.build_patch(
            task(),
            snapshot,
            settings=settings,
            run_dir=paths.runtime_root / "runs" / str(created["task_id"]),
        )
    agents.cleanup_worktree(snapshot.worktree, paths=paths, force=True)


def test_patch_requires_matching_review_receipt_before_apply(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
) -> None:
    paths, settings = local_repo
    run, snapshot, _ = prepare_patch_run(paths, settings)

    with pytest.raises(agents.CoordinatorError, match="approval"):
        agents.apply_run(
            str(run["task_id"]),
            release_check=False,
            settings=settings,
            paths=paths,
        )
    agents.cleanup_worktree(snapshot.worktree, paths=paths, force=True)


def test_stale_touched_file_blocks_apply_without_merging(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
) -> None:
    paths, settings = local_repo
    run, snapshot, _ = prepare_patch_run(paths, settings)
    approved = agents.approve_run(
        str(run["task_id"]), reviewed_by="main-codex", paths=paths
    )
    (paths.repo_root / "tools" / "example.py").write_text(
        "VALUE = 99\n", encoding="utf-8"
    )

    with pytest.raises(agents.CoordinatorError, match="stale"):
        agents.apply_run(
            str(approved["task_id"]),
            release_check=False,
            settings=settings,
            paths=paths,
        )
    stale = agents.get_run(str(run["task_id"]), db_path=paths.db_path)
    assert stale is not None
    assert stale["status"] == "stale"
    assert (paths.repo_root / "tools" / "example.py").read_text() == "VALUE = 99\n"
    agents.cleanup_worktree(snapshot.worktree, paths=paths, force=True)


def test_reviewed_patch_applies_without_staging_or_committing(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
) -> None:
    paths, settings = local_repo
    run, _, _ = prepare_patch_run(paths, settings)
    assert "VALUE = 2" in run["patch_preview"]
    assert run["patch_preview_truncated"] is False
    head_before = git(paths.repo_root, "rev-parse", "HEAD")
    approved = agents.approve_run(
        str(run["task_id"]), reviewed_by="main-codex", paths=paths
    )

    applied = agents.apply_run(
        str(approved["task_id"]),
        release_check=False,
        settings=settings,
        paths=paths,
    )

    assert applied["status"] == "applied"
    assert (paths.repo_root / "tools" / "example.py").read_text() == "VALUE = 2\n"
    assert git(paths.repo_root, "rev-parse", "HEAD") == head_before
    assert git(paths.repo_root, "diff", "--cached", "--name-only") == ""
    assert not Path(str(applied["worktree_path"])).exists()
    assert Path(str(applied["safety"]["backup_path"])).is_dir()


def test_cancel_marks_run_and_terminates_child_group(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
) -> None:
    paths, settings = local_repo
    created = agents.create_run(
        task(role="explorer", allowed_paths=["."]),
        settings=settings,
        paths=paths,
    )
    child = subprocess.Popen(["sleep", "30"], start_new_session=True)
    agents._update_run(
        str(created["task_id"]),
        db_path=paths.db_path,
        status="running",
        phase="explorer",
        child_pid=child.pid,
    )
    cancelled = agents.cancel_run(str(created["task_id"]), paths=paths)
    child.wait(timeout=3)
    assert cancelled["cancel_requested"] is True
    assert child.returncode == -signal.SIGTERM


def test_model_process_slot_is_serial_across_workers(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
) -> None:
    paths, _ = local_repo
    first_entered = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    second_entered = threading.Event()

    def first_worker() -> None:
        with agents.serial_model_slot(paths):
            first_entered.set()
            assert release_first.wait(timeout=2)

    def second_worker() -> None:
        second_started.set()
        with agents.serial_model_slot(paths):
            second_entered.set()

    first = threading.Thread(target=first_worker)
    second = threading.Thread(target=second_worker)
    first.start()
    assert first_entered.wait(timeout=2)
    second.start()
    assert second_started.wait(timeout=2)
    assert not second_entered.wait(timeout=0.1)
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)
    assert second_entered.is_set()


def test_sandbox_profile_blocks_home_and_allows_only_local_ollama(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
) -> None:
    paths, _ = local_repo
    run_dir = paths.runtime_root / "run"
    run_dir.mkdir(parents=True)
    profile = agents.build_sandbox_profile(
        worktree=paths.repo_root,
        run_dir=run_dir,
        paths=paths,
        allow_worktree_writes=False,
    )
    assert "(deny network-outbound)" in profile
    assert '(remote ip "localhost:11434")' in profile
    assert f'(deny file-read-data (require-all (subpath "{Path.home()}")' in profile
    assert (
        f'(deny file-map-executable (require-all (subpath "{Path.home()}")'
        in profile
    )
    assert f'(require-not (subpath "{paths.repo_root}"))' in profile
    assert str(paths.repo_root) in profile
    assert f'(require-not (subpath "{paths.repo_root / ".git"}"))' not in profile
    assert f'(deny file-write* (subpath "{paths.repo_root / ".git"}"))' in profile


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS Seatbelt integration")
def test_process_parses_json_despite_stderr_warning(
    local_repo: tuple[agents.CoordinatorPaths, agents.LocalAgentSettings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, settings = local_repo
    fake = paths.repo_root / "fake-codex"
    fake.write_text(
        """#!/usr/bin/python3
import json, pathlib, sys
target = pathlib.Path(sys.argv[sys.argv.index('--output-last-message') + 1])
target.write_text(json.dumps({
  'schema_version': 'career_local_dev_agent_response_v1',
  'status': 'completed',
  'summary': 'Local response is valid.',
  'details': [], 'risks': [], 'blocking_reason': None,
  'findings': [], 'requested_checks': []
}))
print('warning from local tool', file=sys.stderr)
print('{}')
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    real_which = shutil.which
    monkeypatch.setattr(
        agents.shutil,
        "which",
        lambda name: str(fake) if name == "codex" else real_which(name),
    )
    created = agents.create_run(
        task(role="explorer", allowed_paths=["."]),
        settings=settings,
        paths=paths,
    )
    run_dir = paths.runtime_root / "runs" / str(created["task_id"])
    response = agents.run_agent_process(
        task_id=str(created["task_id"]),
        role="explorer",
        model=settings.roles["explorer"].model,
        label="fake",
        prompt="{}",
        worktree=paths.repo_root,
        run_dir=run_dir,
        timeout_seconds=5,
        settings=settings,
        paths=paths,
    )
    assert response.summary == "Local response is valid."
    assert "warning from local tool" in (run_dir / "fake" / "stderr.log").read_text()


def test_stream_redaction_removes_environment_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRIVATE_API_KEY", "abcdefgh-super-secret")
    redacted = agents._redact_stream(
        "PRIVATE_API_KEY=abcdefgh-super-secret token=plain-value"
    )
    assert "abcdefgh-super-secret" not in redacted
    assert "plain-value" not in redacted
    assert redacted.count("<redacted>") == 2
