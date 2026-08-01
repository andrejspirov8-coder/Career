"""Review receipts, backups, autonomy state, and safety accounting."""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from career_job_search.dev_agents.common import (
    AUTO_APPLY_POLICY_VERSION,
    CoordinatorError,
    CoordinatorPaths,
    _json_dump,
    atomic_write_json,
    atomic_write_text,
    utc_now_iso,
)
from career_job_search.dev_agents.models import (
    AgentTaskSpec,
    LocalAgentSettings,
    normalise_relative_path,
)
from career_job_search.dev_agents.proposals import get_proposal
from career_job_search.dev_agents.runs import (
    _update_run,
    connect,
    get_rollout,
    get_run,
)
from career_job_search.dev_agents.snapshots import _git, _git_bytes, _zlist


def _load_task_input(task_file: Path | None, task_json: str | None) -> AgentTaskSpec:
    if task_file is not None:
        if not task_file.is_file():
            raise CoordinatorError(f"Task file does not exist: {task_file}")
        raw = task_file.read_text(encoding="utf-8")
    elif task_json is not None:
        raw = task_json
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        raise CoordinatorError(
            "Provide --task-file, --task-json, or task JSON on stdin."
        )
    try:
        return AgentTaskSpec.model_validate_json(raw)
    except ValidationError as exc:
        raise CoordinatorError(f"Invalid local-agent task: {exc}") from exc


def _manifest_for_run(
    run: dict[str, Any], *, paths: CoordinatorPaths
) -> dict[str, Any]:
    path = paths.runtime_root / "runs" / run["task_id"] / "snapshot-manifest.json"
    if not path.is_file():
        raise CoordinatorError("Snapshot manifest is missing.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoordinatorError("Snapshot manifest is invalid.") from exc


def _assert_patch_fresh(run: dict[str, Any], *, paths: CoordinatorPaths) -> None:
    manifest = _manifest_for_run(run, paths=paths)
    files = manifest.get("files", {})
    changed_files = run.get("result", {}).get("changed_files", [])
    if not isinstance(changed_files, list) or not changed_files:
        raise CoordinatorError("Run has no coordinator-computed changed files.")
    for raw_path in changed_files:
        path = normalise_relative_path(str(raw_path))
        active = paths.repo_root / path
        baseline = files.get(path)
        if baseline is None:
            if active.exists() or active.is_symlink():
                raise CoordinatorError(f"Patch is stale; new path now exists: {path}")
            continue
        if not active.exists() and not active.is_symlink():
            raise CoordinatorError(f"Patch is stale; active path is missing: {path}")
        current = _git(
            ["hash-object", "--no-filters", "--", path], cwd=paths.repo_root
        ).stdout.strip()
        if current != baseline.get("object_id"):
            raise CoordinatorError(f"Patch is stale; active path changed: {path}")


def _is_auto_apply_path(category: str, path: str) -> bool:
    clean = normalise_relative_path(path, allow_root=False)
    if category == "documentation":
        return clean.startswith("docs/") and clean.endswith(".md")
    if category != "tests":
        return False
    return bool(
        (clean.startswith("tests/test_") and clean.endswith(".py"))
        or (
            clean.startswith("dashboard/")
            and (
                clean.endswith(".test.ts")
                or clean.endswith(".test.tsx")
                or clean.startswith("dashboard/e2e/")
            )
        )
    )


def auto_apply_eligibility(
    run: dict[str, Any],
    *,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
    require_secondary_review: bool = True,
) -> dict[str, Any]:
    reasons: list[str] = []
    autonomy = evaluate_autonomy(settings=settings, paths=paths)
    if not autonomy["auto_apply_enabled"]:
        reasons.append("Tier 2 auto-apply is not enabled")
    proposal_id = run.get("proposal_id")
    proposal = (
        get_proposal(str(proposal_id), db_path=paths.db_path) if proposal_id else None
    )
    if proposal is None:
        reasons.append("run did not come from an approved planner proposal")
        category = ""
    else:
        category = str(proposal["category"])
        if category not in settings.autonomy.auto_apply_categories:
            reasons.append("proposal category requires Main Codex review")
    task = run.get("task", {})
    if task.get("risk") != "low":
        reasons.append("only low-risk tasks can auto-apply")
    if not task.get("acceptance_checks"):
        reasons.append("a deterministic check is required")
    changed_files = run.get("result", {}).get("changed_files", [])
    diff_lines = int(run.get("result", {}).get("diff_lines") or 0)
    if not changed_files:
        reasons.append("patch has no coordinator-computed changed files")
    if len(changed_files) > settings.autonomy.auto_apply_max_files:
        reasons.append("patch exceeds the auto-apply file limit")
    if diff_lines > settings.autonomy.auto_apply_max_diff_lines:
        reasons.append("patch exceeds the auto-apply line limit")
    statuses = run.get("result", {}).get("change_statuses", {})
    if any(status not in {"A", "M"} for status in statuses.values()):
        reasons.append("auto-apply permits additions and modifications only")
    if category and any(
        not _is_auto_apply_path(category, str(path)) for path in changed_files
    ):
        reasons.append("patch leaves the documentation/test auto-apply allowlist")
    primary_findings = run.get("local_review", {}).get("findings", [])
    if any(
        finding.get("severity") in {"critical", "major"}
        for finding in primary_findings
        if isinstance(finding, dict)
    ):
        reasons.append("primary reviewer reported a blocking finding")
    if require_secondary_review:
        secondary = run.get("secondary_review", {})
        if not secondary:
            reasons.append("independent secondary review has not completed")
        elif secondary.get("status") != "completed" or any(
            finding.get("severity") in {"critical", "major"}
            for finding in secondary.get("findings", [])
            if isinstance(finding, dict)
        ):
            reasons.append("secondary reviewer did not approve the patch")
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "category": category or None,
        "autonomy": autonomy,
    }


def approve_run(
    task_id: str,
    *,
    reviewed_by: str,
    paths: CoordinatorPaths,
    settings: LocalAgentSettings | None = None,
) -> dict[str, Any]:
    run = get_run(task_id, db_path=paths.db_path)
    if run is None:
        raise CoordinatorError("Local-agent run was not found.")
    if run["status"] != "ready_for_codex_review":
        raise CoordinatorError("Only a verified patch can be approved.")
    if run["role"] != "implementer" or not run.get("patch_path"):
        raise CoordinatorError(
            "Read-only agent results do not have an applicable patch."
        )
    if reviewed_by not in {"main-codex", AUTO_APPLY_POLICY_VERSION}:
        raise CoordinatorError("Unsupported local-agent reviewer identity.")
    if reviewed_by == AUTO_APPLY_POLICY_VERSION:
        if settings is None:
            raise CoordinatorError("Auto-apply approval requires coordinator policy.")
        eligibility = auto_apply_eligibility(
            run, settings=settings, paths=paths, require_secondary_review=True
        )
        if not eligibility["eligible"]:
            raise CoordinatorError(
                "Auto-apply policy rejected the patch: "
                + "; ".join(eligibility["reasons"])
            )
    patch_path = Path(str(run["patch_path"]))
    digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
    if digest != run.get("patch_sha256"):
        raise CoordinatorError("Patch changed after verification; rerun the task.")
    _update_run(
        task_id,
        db_path=paths.db_path,
        status="approved",
        phase="approved",
        reviewed_patch_sha256=digest,
        reviewed_by=reviewed_by,
        reviewed_at=utc_now_iso(),
        approval_policy=reviewed_by,
        auto_apply_receipt_json=(
            _json_dump(
                {
                    "schema": "career_local_auto_apply_receipt_v1",
                    "policy": AUTO_APPLY_POLICY_VERSION,
                    "patch_sha256": digest,
                    "approved_at": utc_now_iso(),
                    "primary_reviewer": run.get("local_review", {}).get("model"),
                    "secondary_reviewer": run.get("secondary_review", {}).get("model"),
                }
            )
            if reviewed_by == AUTO_APPLY_POLICY_VERSION
            else "{}"
        ),
    )
    approved = get_run(task_id, db_path=paths.db_path)
    if approved is None:
        raise CoordinatorError("Approved run disappeared.")
    return approved


def create_workspace_backup(*, task_id: str, paths: CoordinatorPaths) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = paths.backup_root / f"{task_id}-{stamp}"
    destination.mkdir(parents=True, exist_ok=False)
    destination.chmod(0o700)
    _git(
        [
            "diff",
            "--binary",
            "--no-ext-diff",
            "HEAD",
            f"--output={destination / 'tracked.patch'}",
        ],
        cwd=paths.repo_root,
    )
    status = _git_bytes(["status", "--porcelain=v2", "-z"], cwd=paths.repo_root)
    (destination / "status-before.zlist").write_bytes(status)
    untracked = _zlist(
        _git_bytes(
            ["ls-files", "-z", "--others", "--exclude-standard"],
            cwd=paths.repo_root,
        )
    )
    atomic_write_json(destination / "untracked-files.json", untracked)
    with tarfile.open(destination / "untracked-files.tar.gz", "w:gz") as archive:
        for path in untracked:
            source = paths.repo_root / path
            if source.exists() or source.is_symlink():
                archive.add(source, arcname=path, recursive=False)
    checksums: list[str] = []
    for filename in ("tracked.patch", "untracked-files.tar.gz"):
        artifact = destination / filename
        checksums.append(
            f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {filename}"
        )
    atomic_write_text(destination / "SHA256SUMS", "\n".join(checksums) + "\n")
    return destination


def evaluate_autonomy(
    *, settings: LocalAgentSettings, paths: CoordinatorPaths
) -> dict[str, Any]:
    rollout = get_rollout(settings=settings, db_path=paths.db_path)
    safe_runs = int(rollout["safe_applied_runs"])
    safe_streak = int(rollout["safe_apply_streak"])
    selected_model = rollout.get("selected_implementer_model")
    selected_digest = rollout.get("selected_implementer_digest")
    with connect(paths.db_path) as con:
        recent = con.execute(
            """
            SELECT first_pass_ok, error FROM local_agent_runs
            WHERE role = 'implementer' AND status = 'applied'
              AND model = ? AND model_digest = ?
            ORDER BY finished_at DESC LIMIT ?
            """,
            (
                selected_model,
                selected_digest,
                settings.autonomy.rolling_window,
            ),
        ).fetchall()
        current = con.execute(
            "SELECT * FROM local_agent_autonomy WHERE id = 1"
        ).fetchone()
    rolling_total = len(recent)
    rolling_first_pass = sum(
        1 for row in recent if bool(row["first_pass_ok"]) and not row["error"]
    )
    rolling_rate = round(rolling_first_pass / max(rolling_total, 1), 3)
    tier = 0
    if (
        rollout.get("qualified_at")
        and safe_runs >= settings.autonomy.tier_one_safe_runs
    ):
        tier = 1
    if (
        tier == 1
        and safe_streak >= settings.autonomy.tier_two_safe_runs
        and rolling_total >= settings.autonomy.rolling_window
        and rolling_rate >= settings.autonomy.minimum_first_pass_rate
    ):
        tier = 2
    manually_paused = bool(current["manually_paused"]) if current else False
    paused_reason = str(current["paused_reason"] or "") if current else ""
    auto_apply_enabled = tier >= 2 and not manually_paused
    now = utc_now_iso()
    with connect(paths.db_path) as con:
        con.execute(
            """
            UPDATE local_agent_autonomy
            SET tier = ?, auto_apply_enabled = ?, last_evaluated_at = ?, updated_at = ?
            WHERE id = 1
            """,
            (tier, 1 if auto_apply_enabled else 0, now, now),
        )
        con.execute(
            """
            UPDATE local_agent_settings
            SET safe_applied_runs = ?, local_first_enabled = ?, updated_at = ?
            WHERE id = 1
            """,
            (safe_runs, 1 if tier >= 1 else 0, now),
        )
    return {
        "tier": tier,
        "auto_apply_enabled": auto_apply_enabled,
        "manually_paused": manually_paused,
        "paused_reason": paused_reason,
        "safe_applied_runs": safe_runs,
        "safe_apply_streak": safe_streak,
        "rolling_window": settings.autonomy.rolling_window,
        "rolling_first_pass_rate": rolling_rate,
        "tier_one_required": settings.autonomy.tier_one_safe_runs,
        "tier_two_required": settings.autonomy.tier_two_safe_runs,
        "minimum_first_pass_rate": settings.autonomy.minimum_first_pass_rate,
        "evaluated_at": now,
    }


def set_autonomy_paused(
    paused: bool,
    *,
    reason: str,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
) -> dict[str, Any]:
    now = utc_now_iso()
    clean_reason = reason.strip()[:1000] if paused else ""
    with connect(paths.db_path) as con:
        con.execute(
            """
            UPDATE local_agent_autonomy
            SET manually_paused = ?, paused_reason = ?, auto_apply_enabled = 0,
                updated_at = ?
            WHERE id = 1
            """,
            (1 if paused else 0, clean_reason, now),
        )
    result = evaluate_autonomy(settings=settings, paths=paths)
    if not paused and result["tier"] < 2:
        with connect(paths.db_path) as con:
            con.execute(
                """
                UPDATE local_agent_autonomy
                SET manually_paused = 1,
                    paused_reason = 'Tier 2 safety thresholds are not yet met',
                    auto_apply_enabled = 0, updated_at = ?
                WHERE id = 1
                """,
                (utc_now_iso(),),
            )
        raise CoordinatorError(
            "Auto-apply cannot resume until the Tier 2 safety thresholds are met."
        )
    return result


def _record_apply_result(
    task_id: str,
    *,
    safe: bool,
    first_pass: bool,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
) -> None:
    run = get_run(task_id, db_path=paths.db_path, include_streams=False)
    if run is None:
        raise CoordinatorError("Applied run disappeared before rollout accounting.")
    model = str(run["model"])
    digest = str(run.get("model_digest") or "")
    if not digest:
        raise CoordinatorError("Applied run has no pinned model digest.")
    now = utc_now_iso()
    with connect(paths.db_path) as con:
        con.execute(
            """
            INSERT INTO local_agent_model_qualifications(
              model_tag, model_digest, qualified, updated_at
            ) VALUES (?, ?, 0, ?)
            ON CONFLICT(model_tag, model_digest) DO NOTHING
            """,
            (model, digest, now),
        )
        con.execute(
            """
            UPDATE local_agent_model_qualifications
            SET total_applied_runs = total_applied_runs + 1,
                first_pass_applied_runs = first_pass_applied_runs + ?,
                safe_applied_runs = safe_applied_runs + ?,
                safe_apply_streak = CASE
                  WHEN ? = 1 THEN safe_apply_streak + 1 ELSE 0 END,
                updated_at = ?
            WHERE model_tag = ? AND model_digest = ?
            """,
            (
                1 if first_pass and safe else 0,
                1 if safe else 0,
                1 if safe else 0,
                now,
                model,
                digest,
            ),
        )
        con.execute(
            "UPDATE local_agent_runs SET first_pass_ok = ? WHERE task_id = ?",
            (1 if first_pass and safe else 0, task_id),
        )
    evaluate_autonomy(settings=settings, paths=paths)


def record_model_safety_violation(
    model: str,
    digest: str,
    *,
    privacy: bool,
    reason: str,
    settings: LocalAgentSettings,
    paths: CoordinatorPaths,
) -> None:
    now = utc_now_iso()
    with connect(paths.db_path) as con:
        con.execute(
            """
            INSERT INTO local_agent_model_qualifications(
              model_tag, model_digest, qualified, updated_at
            ) VALUES (?, ?, 0, ?)
            ON CONFLICT(model_tag, model_digest) DO NOTHING
            """,
            (model, digest, now),
        )
        con.execute(
            """
            UPDATE local_agent_model_qualifications
            SET scope_violations = scope_violations + ?,
                privacy_violations = privacy_violations + ?,
                safe_apply_streak = 0, updated_at = ?
            WHERE model_tag = ? AND model_digest = ?
            """,
            (0 if privacy else 1, 1 if privacy else 0, now, model, digest),
        )
    set_autonomy_paused(
        True,
        reason=reason,
        settings=settings,
        paths=paths,
    )
