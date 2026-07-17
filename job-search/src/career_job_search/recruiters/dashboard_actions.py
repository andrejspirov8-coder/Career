"""Safe recruiter note, status, and dry-run dashboard actions."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from career_job_search.core.time import utc_now_iso
from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.paths import (
    HIRING_NETWORK_ACTION_PLAN_JSONL,
    JOB_ROOT,
)
from career_job_search.recruiters.dashboard_storage import (
    ACTION_HISTORY_JSONL,
    RUNTIME_DIR,
    _append_dashboard_action_history,
    _lock_path,
    _profile_history_key,
    _row_status,
    _write_run_history,
    read_jsonl_records,
    write_jsonl_records,
)
from career_job_search.recruiters.dispatch_guard import validate_note_integrity
from career_job_search.recruiters.repository import (
    DEFAULT_STATE_DB,
    approval_check,
    approve_invite,
    mark_sent,
    record_operator_action,
)

MAX_NOTE_CHARS = 280
UNSAFE_COMMAND_TOKENS = frozenset(
    {"--allow-live-dispatch", "--full-auto", "--auto-send"}
)
SAFE_ACTIONS: dict[str, list[str]] = {
    "preflight": [sys.executable, "tools/hiring_network_workflow.py", "preflight"],
    "search_rank": [
        sys.executable,
        "tools/hiring_network_workflow.py",
        "graph",
        "run",
        "--dry-run",
        "--stage",
        "all",
    ],
    "rank_existing": [
        sys.executable,
        "tools/hiring_network_workflow.py",
        "rank",
    ],
    "dispatch_dry_run": [
        sys.executable,
        "tools/hiring_network_workflow.py",
        "dispatch",
        "--dry-run",
        "--max",
        "3",
    ],
}


def validate_dashboard_note(note: str) -> str:
    clean = " ".join((note or "").split())
    if not clean:
        raise ValueError("Note is required.")
    if len(clean) > MAX_NOTE_CHARS:
        raise ValueError(f"Note must be {MAX_NOTE_CHARS} characters or fewer.")
    ok, reason = validate_note_integrity(clean)
    if not ok:
        raise ValueError(reason)
    return clean


def update_action_plan_note(
    *,
    profile_url: str,
    note: str,
    action_plan_path: Path = HIRING_NETWORK_ACTION_PLAN_JSONL,
    action_history_path: Path = ACTION_HISTORY_JSONL,
) -> dict[str, Any]:
    canon = lis.canonical_profile_url(profile_url)
    if not canon:
        raise ValueError("A valid LinkedIn profile URL is required.")
    clean_note = validate_dashboard_note(note)
    rows, _malformed = read_jsonl_records(action_plan_path)
    updated = False
    for row in rows:
        row_url = lis.canonical_profile_url(str(row.get("profile_url") or ""))
        if row_url != canon:
            continue
        old_reason = str(row.get("note_reason") or "").strip()
        old_status = _row_status(row)
        row["note"] = clean_note
        row["note_reason"] = (
            f"{old_reason}:dashboard_edit" if old_reason else "dashboard_edit"
        )
        row["dashboard_edited_at"] = utc_now_iso()
        updated = True
        break
    if not updated:
        raise ValueError(f"Profile not found in action plan: {canon}")
    write_jsonl_records(action_plan_path, rows)
    _append_dashboard_action_history(
        action_type="update_note",
        profile_url=canon,
        old_status=old_status,
        new_status=old_status,
        action_history_path=action_history_path,
    )
    return {"updated": True, "profile_url": canon, "note": clean_note}


def approve_dashboard_note(
    *,
    profile_url: str,
    note: str,
    state_db_path: Path = DEFAULT_STATE_DB,
    action_history_path: Path = ACTION_HISTORY_JSONL,
    run_id: str = "dashboard-approval",
) -> dict[str, Any]:
    clean_note = validate_dashboard_note(note)
    note_hash = approve_invite(
        profile_url=profile_url,
        note=clean_note,
        run_id=run_id,
        approved_by="dashboard",
        db_path=state_db_path,
    )
    check = approval_check(
        profile_url=profile_url, note=clean_note, db_path=state_db_path
    )
    _append_dashboard_action_history(
        action_type="approve_note",
        profile_url=profile_url,
        old_status="approval:pending",
        new_status="approval:approved" if check.approved else "approval:failed",
        action_history_path=action_history_path,
    )
    return {
        "approved": check.approved,
        "reason": check.reason,
        "profile_url": lis.canonical_profile_url(profile_url) or profile_url,
        "note_hash": note_hash,
    }


def _target_state(target_status: str) -> tuple[str, str, str]:
    if target_status == "skipped":
        return "skip", "skip", "mark_skipped"
    if target_status == "review":
        return "queue_review", "review", "mark_review"
    if target_status == "approved":
        raise ValueError("Bulk approval is not supported from the dashboard.")
    raise ValueError(f"Unsupported dashboard target status: {target_status}")


def bulk_update_profile_status(
    *,
    profile_urls: list[str],
    target_status: str,
    action_plan_path: Path = HIRING_NETWORK_ACTION_PLAN_JSONL,
    action_history_path: Path = ACTION_HISTORY_JSONL,
    operator_source: str = "dashboard",
) -> dict[str, Any]:
    next_tier, next_decision, action_type = _target_state(target_status)
    wanted = {
        canon for canon in (_profile_history_key(url) for url in profile_urls) if canon
    }
    if not wanted:
        raise ValueError("At least one valid LinkedIn profile URL is required.")

    rows, _malformed = read_jsonl_records(action_plan_path)
    updated: list[str] = []
    history_events: list[tuple[str, str, str]] = []
    for row in rows:
        canon = _profile_history_key(str(row.get("profile_url") or ""))
        if canon not in wanted:
            continue
        old_status = _row_status(row)
        row["send_tier"] = next_tier
        row["decision"] = next_decision
        row["dashboard_status_updated_at"] = utc_now_iso()
        row["dashboard_status_source"] = operator_source
        updated.append(canon)
        history_events.append((canon, old_status, _row_status(row)))

    if not updated:
        raise ValueError("No matching profiles found in action plan.")
    write_jsonl_records(action_plan_path, rows)
    for profile_url, old_status, new_status in history_events:
        _append_dashboard_action_history(
            action_type=action_type,
            profile_url=profile_url,
            old_status=old_status,
            new_status=new_status,
            action_history_path=action_history_path,
            operator_source=operator_source,
        )
    return {
        "updated": True,
        "updated_count": len(updated),
        "profile_urls": updated,
        "target_status": target_status,
    }


def mark_profile_skipped(
    *,
    profile_url: str,
    action_plan_path: Path = HIRING_NETWORK_ACTION_PLAN_JSONL,
    action_history_path: Path = ACTION_HISTORY_JSONL,
) -> dict[str, Any]:
    return bulk_update_profile_status(
        profile_urls=[profile_url],
        target_status="skipped",
        action_plan_path=action_plan_path,
        action_history_path=action_history_path,
    )


def mark_profile_review(
    *,
    profile_url: str,
    action_plan_path: Path = HIRING_NETWORK_ACTION_PLAN_JSONL,
    action_history_path: Path = ACTION_HISTORY_JSONL,
) -> dict[str, Any]:
    return bulk_update_profile_status(
        profile_urls=[profile_url],
        target_status="review",
        action_plan_path=action_plan_path,
        action_history_path=action_history_path,
    )


SAFE_OPERATOR_ACTIONS = frozenset(
    {
        "copy_note_recorded",
        "mark_sent_manual",
        "mark_pending",
        "mark_replied",
        "mark_accepted",
        "mark_rejected",
        "snooze_followup",
    }
)


def record_dashboard_operator_action(
    *,
    action_type: str,
    profile_url: str,
    note: str = "",
    action_history_path: Path = ACTION_HISTORY_JSONL,
    state_db_path: Path = DEFAULT_STATE_DB,
    operator_source: str = "dashboard",
) -> dict[str, Any]:
    if action_type not in SAFE_OPERATOR_ACTIONS:
        raise ValueError(f"Unsupported dashboard operator action: {action_type}")
    canon = _profile_history_key(profile_url)
    if not canon:
        raise ValueError("A valid LinkedIn profile URL is required.")

    clean_note = ""
    if action_type in {"copy_note_recorded", "mark_sent_manual"}:
        clean_note = validate_dashboard_note(note)
    elif note:
        clean_note = " ".join(note.split())

    if action_type == "mark_sent_manual":
        mark_sent(
            profile_url=canon,
            note=clean_note,
            run_id="dashboard-manual-send",
            reason="manual_send_recorded",
            metadata={"operator_source": operator_source},
            db_path=state_db_path,
        )

    state_event = record_operator_action(
        action_type=action_type,
        profile_url=canon,
        note=clean_note,
        operator_source=operator_source,
        metadata={"source": "dashboard"},
        db_path=state_db_path,
    )
    history_event = _append_dashboard_action_history(
        action_type=action_type,
        profile_url=canon,
        old_status="operator:pending",
        new_status=f"operator:{action_type}",
        action_history_path=action_history_path,
        operator_source=operator_source,
    )
    return {
        "recorded": True,
        "action_type": action_type,
        "profile_url": canon,
        "note_hash": state_event.get("note_hash") or "",
        "history": history_event,
    }


def _assert_safe_command(command: list[str]) -> None:
    if any(token in UNSAFE_COMMAND_TOKENS for token in command):
        raise ValueError("Unsafe dashboard command contains a live-dispatch flag.")


def run_dashboard_action(
    action: str,
    *,
    runtime_dir: Path = RUNTIME_DIR,
    command_override: list[str] | None = None,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    if action not in SAFE_ACTIONS:
        raise ValueError(f"Unsupported dashboard action: {action}")
    command = list(command_override or SAFE_ACTIONS[action])
    _assert_safe_command(command)

    runtime_dir.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(runtime_dir)
    try:
        fd = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise RuntimeError(
            "Another dashboard automation action is already running."
        ) from exc

    started_at = utc_now_iso()
    try:
        with fd:
            fd.write(json.dumps({"action": action, "started_at": started_at}) + "\n")
        completed = subprocess.run(
            command,
            cwd=JOB_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        result = {
            "action": action,
            "command": command,
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "returncode": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
        }
        _write_run_history(runtime_dir, result)
        return result
    finally:
        lock.unlink(missing_ok=True)
