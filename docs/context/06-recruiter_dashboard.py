#!/usr/bin/env python3
"""Safe JSON helper for the local recruiter dashboard.

The dashboard may inspect queues, approve exact notes, edit queued notes, and
run dry-run workflow commands. It deliberately cannot trigger live LinkedIn
dispatch.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import linkedin_selectors as lis
from recruiter_dispatch_guard import validate_note_integrity
from recruiter_linkedin_paths import (
    HIRING_NETWORK_ACTION_PLAN_JSONL,
    HIRING_NETWORK_RUN_STATE_JSON,
    JOB_ROOT,
    RECRUITERS_CSV,
)
from recruiter_policy import current_send_mode, risk_stop_state
from recruiter_state import (
    DEFAULT_STATE_DB,
    approval_check,
    approval_metadata,
    approve_invite,
    latest_approval_metadata,
    mark_sent,
    record_operator_action,
)

SCHEMA = "recruiter_dashboard_overview_v1"
RUNTIME_DIR = JOB_ROOT / "runtime" / "dashboard-runs"
ACTION_HISTORY_JSONL = RUNTIME_DIR / "dashboard-action-history.jsonl"
PERSONA_STATS_JSON = JOB_ROOT / "pipeline" / "persona_stats.json"
MAX_NOTE_CHARS = 280
RUN_HISTORY_LIMIT = 5

UNSAFE_COMMAND_TOKENS = frozenset(
    {
        "--allow-live-dispatch",
        "--full-auto",
        "--auto-send",
    }
)

SAFE_ACTIONS: dict[str, list[str]] = {
    "preflight": [
        sys.executable,
        "tools/hiring_network_workflow.py",
        "preflight",
    ],
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
        "5",
    ],
}


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def json_response(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _load_json(path: Path) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _active_run(runtime_dir: Path) -> dict[str, Any] | None:
    lock = _lock_path(runtime_dir)
    data = _load_json(lock)
    if isinstance(data, dict):
        return data
    if lock.exists():
        return {"error": "malformed_lock", "path": str(lock)}
    return None


def _recent_runs(runtime_dir: Path, limit: int = RUN_HISTORY_LIMIT) -> list[dict[str, Any]]:
    if not runtime_dir.exists():
        return []
    runs: list[dict[str, Any]] = []
    for path in sorted(runtime_dir.glob("run-*.json"), key=lambda item: item.name, reverse=True):
        data = _load_json(path)
        if not isinstance(data, dict):
            continue
        runs.append(data)
        if len(runs) >= limit:
            break
    return runs


def _write_run_history(runtime_dir: Path, result: dict[str, Any]) -> None:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    action = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-"
        for char in str(result.get("action") or "action")
    )
    path = runtime_dir / f"run-{stamp}-{action}.json"
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def read_jsonl_records(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists() or path.stat().st_size == 0:
        return [], 0
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return [], 0
    if raw.startswith("["):
        data = _load_json(path)
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)], 0
        return [], 1

    rows: list[dict[str, Any]] = []
    malformed = 0
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(obj, dict):
            rows.append(obj)
        else:
            malformed += 1
    return rows, malformed


def write_jsonl_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def read_dashboard_action_history(path: Path = ACTION_HISTORY_JSONL) -> list[dict[str, Any]]:
    rows, _malformed = read_jsonl_records(path)
    return rows


def _profile_history_key(profile_url: str) -> str:
    return lis.canonical_profile_url(profile_url) or profile_url


def _history_by_profile(path: Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in read_dashboard_action_history(path):
        key = _profile_history_key(str(row.get("profile_url") or ""))
        if key:
            grouped[key].append(row)
    return dict(grouped)


def _append_dashboard_action_history(
    *,
    action_type: str,
    profile_url: str,
    old_status: str,
    new_status: str,
    action_history_path: Path = ACTION_HISTORY_JSONL,
    operator_source: str = "dashboard",
) -> dict[str, Any]:
    canon = _profile_history_key(profile_url)
    record = {
        "action_type": action_type,
        "profile_url": canon,
        "timestamp": utc_now_iso(),
        "old_status": old_status,
        "new_status": new_status,
        "operator_source": operator_source,
    }
    action_history_path.parent.mkdir(parents=True, exist_ok=True)
    with action_history_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_recruiter_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _risk_flags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _approval_payload(row: dict[str, Any], db_path: Path) -> dict[str, Any]:
    profile_url = str(row.get("profile_url") or "")
    note = str(row.get("note") or "")
    check = approval_check(profile_url=profile_url, note=note, db_path=db_path)
    metadata = approval_metadata(profile_url=profile_url, note=note, db_path=db_path)
    payload = {
        "approved": check.approved,
        "reason": check.reason,
        "note_hash": check.note_hash,
        **metadata,
    }
    if not check.approved and check.reason == "missing_matching_approval":
        previous = latest_approval_metadata(profile_url=profile_url, db_path=db_path)
        if previous:
            payload["warning"] = "note_changed_after_approval"
            payload["previous_note_hash"] = previous.get("note_hash") or ""
    return payload


def _row_status(row: dict[str, Any]) -> str:
    return f"{str(row.get('send_tier') or '')}:{str(row.get('decision') or '')}"


def _score_details(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank_score": row.get("rank_score") or row.get("primary_score"),
        "primary_score": row.get("primary_score"),
        "margin_over_second": row.get("margin_over_second"),
        "profile_confidence": row.get("profile_confidence")
        or row.get("persona_confidence"),
        "send_tier": str(row.get("send_tier") or ""),
        "decision": str(row.get("decision") or ""),
        "top_signals": row.get("top_signals") or [],
    }


def _profile_evidence(row: dict[str, Any]) -> dict[str, Any]:
    top_signals = row.get("top_signals") or []
    if not isinstance(top_signals, list):
        top_signals = [str(top_signals)]
    risk_flags = _risk_flags(row.get("risk_flags"))
    location = str(row.get("location") or "")
    company = str(row.get("company") or "")
    persona = str(row.get("persona") or "")
    cv_variant = str(row.get("cv_variant") or row.get("variant_slug") or "")
    source = str(row.get("source_backend") or row.get("source") or "action_plan")
    confidence = row.get("profile_confidence") or row.get("persona_confidence")
    return {
        "source": source,
        "company": {
            "name": company,
            "facts": [item for item in [company, str(row.get("headline") or "")] if item],
        },
        "persona": {
            "label": persona,
            "evidence": [item for item in [persona, *[str(signal) for signal in top_signals]] if item],
        },
        "cv_fit": {
            "variant": cv_variant,
            "score": row.get("primary_score") or row.get("rank_score"),
            "evidence": [str(signal) for signal in top_signals if str(signal).strip()],
        },
        "geo": {
            "location": location,
            "evidence": [location] if location else [],
        },
        "risk_flags": risk_flags,
        "confidence": confidence,
    }


def _score_explanation(row: dict[str, Any]) -> dict[str, str]:
    decision = str(row.get("decision") or "")
    tier = str(row.get("send_tier") or "")
    persona = str(row.get("persona") or "this profile")
    cv_variant = str(row.get("cv_variant") or row.get("variant_slug") or "the selected CV")
    signals = row.get("top_signals") or []
    if not isinstance(signals, list):
        signals = [str(signals)]
    reason = ", ".join(str(signal) for signal in signals[:3] if str(signal).strip())
    if not reason:
        reason = "the available ranking fields"
    if decision == "skip" or tier == "skip":
        review_reason = "Skip because the score or risk flags are weak."
    elif decision == "approved" or tier == "auto_send":
        review_reason = "Ready for manual send after approval checks."
    else:
        review_reason = "Review before approval."
    return {
        "decision": decision,
        "send_tier": tier,
        "why_this_person": f"Matched {persona} using {reason}.",
        "why_this_cv": f"Best fit is {cv_variant}.",
        "why_review_or_skip": review_reason,
    }


def _note_quality(row: dict[str, Any]) -> dict[str, Any]:
    note = str(row.get("note") or "")
    issues: list[str] = []
    if not note.strip():
        issues.append("missing_note")
    if len(note) > MAX_NOTE_CHARS:
        issues.append("too_long")
    ok, reason = validate_note_integrity(note)
    if not ok:
        issues.append(reason)
    return {
        "valid": not issues,
        "length": len(note),
        "max_chars": MAX_NOTE_CHARS,
        "issues": issues,
    }


def _next_action(record: dict[str, Any]) -> str:
    if record.get("status") == "sent" or record.get("score_details", {}).get("send_tier") == "sent":
        return "wait"
    if record.get("risk_flags"):
        return "review"
    if not record.get("note_quality", {}).get("valid"):
        return "edit_note"
    if record.get("approval", {}).get("approved"):
        return "copy_note"
    if record.get("decision") == "skip" or record.get("send_tier") == "skip":
        return "skip_profile"
    return "approve_note"


def _dashboard_record(
    row: dict[str, Any],
    db_path: Path,
    history_by_profile: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    profile_url = str(row.get("profile_url") or "")
    canon = lis.canonical_profile_url(profile_url) or profile_url
    record = {
        "profile_url": canon,
        "name": str(row.get("name") or ""),
        "headline": str(row.get("headline") or ""),
        "company": str(row.get("company") or ""),
        "location": str(row.get("location") or ""),
        "persona": str(row.get("persona") or ""),
        "cv_variant": str(row.get("cv_variant") or row.get("variant_slug") or ""),
        "rank_score": row.get("rank_score"),
        "send_tier": str(row.get("send_tier") or ""),
        "decision": str(row.get("decision") or ""),
        "risk_flags": _risk_flags(row.get("risk_flags")),
        "note": str(row.get("note") or ""),
        "note_reason": str(row.get("note_reason") or ""),
        "source_backend": str(row.get("source_backend") or ""),
        "approval": _approval_payload(row, db_path),
        "score_details": _score_details(row),
        "score_explanation": _score_explanation(row),
        "profile_evidence": _profile_evidence(row),
        "note_quality": _note_quality(row),
        "action_history": (history_by_profile or {}).get(canon, []),
    }
    record["next_action"] = _next_action(record)
    return record


def _queue_key(row: dict[str, Any]) -> str:
    send_tier = str(row.get("send_tier") or "")
    decision = str(row.get("decision") or "")
    if send_tier == "auto_send" and decision == "approved":
        return "auto_send"
    if send_tier == "queue_review" or decision == "review":
        return "review"
    if send_tier == "skip" or decision == "skip":
        return "skipped"
    return "review"


def _build_saved_views(queues: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    action_rows = [
        *queues["auto_send"],
        *queues["review"],
        *queues["skipped"],
    ]
    return {
        "needs_review": queues["review"],
        "auto_send_candidates": queues["auto_send"],
        "approved": [row for row in action_rows if row.get("approval", {}).get("approved")],
        "skipped": queues["skipped"],
        "sent": queues["sent"],
        "risk_flags": [row for row in action_rows if row.get("risk_flags")],
    }


def _campaign_readiness(queues: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    action_rows = [
        *queues["auto_send"],
        *queues["review"],
        *queues["skipped"],
    ]
    ready_for_manual_send = [
        row
        for row in action_rows
        if row.get("approval", {}).get("approved")
        and row.get("note_quality", {}).get("valid")
        and not row.get("risk_flags")
    ]
    stale_notes = [
        row
        for row in action_rows
        if row.get("approval", {}).get("warning") == "note_changed_after_approval"
    ]
    risky_profiles = [row for row in action_rows if row.get("risk_flags")]
    approvals_valid = [row for row in action_rows if row.get("approval", {}).get("approved")]
    return {
        "ready_for_manual_send": len(ready_for_manual_send),
        "approvals_valid": len(approvals_valid),
        "stale_notes": len(stale_notes),
        "risky_profiles": len(risky_profiles),
        "expected_manual_minutes": max(1, len(ready_for_manual_send) * 2)
        if ready_for_manual_send
        else 0,
    }


def build_metrics(
    action_rows: list[dict[str, Any]], recruiter_rows: list[dict[str, str]]
) -> dict[str, Any]:
    personas: dict[str, Counter[str]] = defaultdict(Counter)
    variants: dict[str, Counter[str]] = defaultdict(Counter)
    risk_flags: Counter[str] = Counter()

    for row in action_rows:
        persona = str(row.get("persona") or "(none)")
        variant = str(row.get("cv_variant") or row.get("variant_slug") or "(none)")
        personas[persona]["queued"] += 1
        variants[variant]["queued"] += 1
        for flag in _risk_flags(row.get("risk_flags")):
            risk_flags[flag] += 1

    for row in recruiter_rows:
        persona = (row.get("persona") or "(none)").strip() or "(none)"
        variant = (row.get("variant_slug") or "(none)").strip() or "(none)"
        status = (row.get("status") or "").strip()
        if status == "sent":
            personas[persona]["sent"] += 1
            variants[variant]["sent"] += 1
        if (row.get("accepted_at") or "").strip():
            personas[persona]["accepted"] += 1
            variants[variant]["accepted"] += 1
        if (row.get("reply_at") or "").strip():
            personas[persona]["reply"] += 1
            variants[variant]["reply"] += 1
        if (row.get("interview_at") or "").strip():
            personas[persona]["interview"] += 1
            variants[variant]["interview"] += 1

    def serialise(counter_map: dict[str, Counter[str]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for key, counts in sorted(counter_map.items()):
            sent = int(counts.get("sent", 0))
            accepted = int(counts.get("accepted", 0))
            reply = int(counts.get("reply", 0))
            out[key] = {
                "queued": int(counts.get("queued", 0)),
                "sent": sent,
                "accepted": accepted,
                "reply": reply,
                "interview": int(counts.get("interview", 0)),
                "accept_rate": accepted / sent if sent else 0.0,
                "reply_rate": reply / sent if sent else 0.0,
            }
        return out

    return {
        "personas": serialise(personas),
        "variants": serialise(variants),
        "risk_flags": dict(risk_flags.most_common()),
    }


def build_overview(
    *,
    action_plan_path: Path = HIRING_NETWORK_ACTION_PLAN_JSONL,
    recruiters_csv_path: Path = RECRUITERS_CSV,
    state_db_path: Path = DEFAULT_STATE_DB,
    run_state_path: Path = HIRING_NETWORK_RUN_STATE_JSON,
    persona_stats_path: Path = PERSONA_STATS_JSON,
    runtime_dir: Path = RUNTIME_DIR,
    action_history_path: Path = ACTION_HISTORY_JSONL,
) -> dict[str, Any]:
    action_rows, malformed_rows = read_jsonl_records(action_plan_path)
    recruiter_rows = read_recruiter_rows(recruiters_csv_path)
    queues = {"auto_send": [], "review": [], "skipped": [], "sent": []}
    histories = _history_by_profile(action_history_path)

    approved_notes = 0
    for row in action_rows:
        record = _dashboard_record(row, state_db_path, histories)
        if record["approval"]["approved"]:
            approved_notes += 1
        queues[_queue_key(row)].append(record)

    sent_count = 0
    accepted_count = 0
    reply_count = 0
    interview_count = 0
    for row in recruiter_rows:
        status = (row.get("status") or "").strip()
        if status == "sent":
            sent_count += 1
        if (row.get("accepted_at") or "").strip():
            accepted_count += 1
        if (row.get("reply_at") or "").strip():
            reply_count += 1
        if (row.get("interview_at") or "").strip():
            interview_count += 1
        if status == "sent":
            profile_url = row.get("profile_url") or ""
            sent_note = row.get("final_note") or row.get("note_preview") or ""
            sent_record = {
                "profile_url": profile_url,
                "name": row.get("name") or "",
                "headline": row.get("headline") or "",
                "company": row.get("company") or "",
                "location": row.get("location") or "",
                "persona": row.get("persona") or "",
                "cv_variant": row.get("variant_slug") or "",
                "rank_score": row.get("rank_score") or "",
                "status": status,
                "send_tier": "sent",
                "decision": status,
                "risk_flags": [],
                "note": sent_note,
                "approval": {"approved": False, "reason": "sent_record", "note_hash": ""},
                "score_details": {
                    "rank_score": row.get("rank_score") or "",
                    "send_tier": "sent",
                    "decision": status,
                },
                "score_explanation": {
                    "decision": status,
                    "send_tier": "sent",
                    "why_this_person": "Already recorded as sent.",
                    "why_this_cv": row.get("variant_slug") or "",
                    "why_review_or_skip": "Wait for a response or follow-up.",
                },
                "profile_evidence": _profile_evidence(
                    {
                        "profile_url": profile_url,
                        "name": row.get("name") or "",
                        "headline": row.get("headline") or "",
                        "company": row.get("company") or "",
                        "location": row.get("location") or "",
                        "persona": row.get("persona") or "",
                        "cv_variant": row.get("variant_slug") or "",
                        "source_backend": "recruiters_csv",
                    }
                ),
                "note_quality": _note_quality({"note": sent_note}),
                "next_action": "wait",
                "action_history": histories.get(_profile_history_key(profile_url), []),
            }
            queues["sent"].append(
                sent_record
            )

    saved_views = _build_saved_views(queues)
    queues["saved_views"] = saved_views
    run_history = _recent_runs(runtime_dir)
    send_mode = current_send_mode()
    readiness = _campaign_readiness(queues)
    run_state = _load_json(run_state_path) or {}
    risk_state = risk_stop_state(
        screen_state=str(run_state.get("screen_state") or run_state.get("risk_screen_state") or ""),
        failure_rate=float(run_state.get("failure_rate") or 0.0),
        pending_invites=int(run_state.get("pending_invites") or 0),
        daily_cap_reached=bool(run_state.get("daily_cap_reached") or False),
    )

    return {
        "schema": SCHEMA,
        "generated_at": utc_now_iso(),
        "send_mode": send_mode,
        "files": {
            "action_plan": str(action_plan_path),
            "recruiters_csv": str(recruiters_csv_path),
            "run_state": str(run_state_path),
            "state_db": str(state_db_path),
        },
        "counts": {
            "total_ranked": len(action_rows),
            "auto_send": len(queues["auto_send"]),
            "queue_review": len(queues["review"]),
            "skipped": len(queues["skipped"]),
            "approved_notes": approved_notes,
            "sent": sent_count,
            "accepted": accepted_count,
            "reply": reply_count,
            "interview": interview_count,
            "malformed_action_rows": malformed_rows,
        },
        "queues": queues,
        "metrics": build_metrics(action_rows, recruiter_rows),
        "run_state": run_state,
        "persona_stats": _load_json(persona_stats_path) or {},
        "active_run": _active_run(runtime_dir),
        "recent_runs": run_history,
        "run_history": run_history,
        "campaign": {"readiness": readiness},
        "risk_stop_state": risk_state,
        "live_dispatch": {
            "mode": send_mode,
            "message": (
                "Manual send mode is active. Use Open Profile, Copy Note, and Mark Sent Manually."
                if send_mode == "manual"
                else "CLI-gated live dispatch is available only after exact approval checks."
            ),
            "auto_send_candidates": len(queues["auto_send"]),
            "approved_notes": approved_notes,
            "ready_for_cli_dispatch": send_mode == "cli_gated"
            and bool(queues["auto_send"])
            and approved_notes >= len(queues["auto_send"]),
            "ready_for_manual_send": readiness["ready_for_manual_send"],
        },
        "safe_actions": SAFE_ACTIONS,
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
    check = approval_check(profile_url=profile_url, note=clean_note, db_path=state_db_path)
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
        canon
        for canon in (_profile_history_key(url) for url in profile_urls)
        if canon
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


def _lock_path(runtime_dir: Path) -> Path:
    return runtime_dir / "dashboard-action.lock"


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
        raise RuntimeError("Another dashboard automation action is already running.") from exc

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


def _payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.cmd == "overview":
        return build_overview()
    if args.cmd == "action":
        return run_dashboard_action(args.name)
    if args.cmd == "approve":
        return approve_dashboard_note(profile_url=args.profile_url, note=args.note)
    if args.cmd == "update-note":
        return update_action_plan_note(profile_url=args.profile_url, note=args.note)
    if args.cmd == "mark-skipped":
        return mark_profile_skipped(profile_url=args.profile_url)
    if args.cmd == "mark-review":
        return mark_profile_review(profile_url=args.profile_url)
    if args.cmd == "bulk-mark-skipped":
        return bulk_update_profile_status(
            profile_urls=args.profile_url,
            target_status="skipped",
        )
    if args.cmd == "bulk-mark-review":
        return bulk_update_profile_status(
            profile_urls=args.profile_url,
            target_status="review",
        )
    if args.cmd == "operator-action":
        return record_dashboard_operator_action(
            action_type=args.action_type,
            profile_url=args.profile_url,
            note=args.note,
        )
    raise ValueError(f"Unsupported command: {args.cmd}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recruiter dashboard JSON helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("overview")

    action = sub.add_parser("action")
    action.add_argument("--name", required=True, choices=sorted(SAFE_ACTIONS))

    approve = sub.add_parser("approve")
    approve.add_argument("--profile-url", required=True)
    approve.add_argument("--note", required=True)

    update = sub.add_parser("update-note")
    update.add_argument("--profile-url", required=True)
    update.add_argument("--note", required=True)

    mark_skipped = sub.add_parser("mark-skipped")
    mark_skipped.add_argument("--profile-url", required=True)

    mark_review = sub.add_parser("mark-review")
    mark_review.add_argument("--profile-url", required=True)

    bulk_skipped = sub.add_parser("bulk-mark-skipped")
    bulk_skipped.add_argument("--profile-url", action="append", required=True)

    bulk_review = sub.add_parser("bulk-mark-review")
    bulk_review.add_argument("--profile-url", action="append", required=True)

    operator = sub.add_parser("operator-action")
    operator.add_argument("--action-type", required=True, choices=sorted(SAFE_OPERATOR_ACTIONS))
    operator.add_argument("--profile-url", required=True)
    operator.add_argument("--note", default="")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = _payload_from_args(args)
    except Exception as exc:
        json_response({"ok": False, "error": str(exc)})
        return 1
    json_response({"ok": True, "data": payload})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
