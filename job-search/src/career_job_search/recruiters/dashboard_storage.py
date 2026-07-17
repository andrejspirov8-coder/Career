"""Private file records shared by recruiter dashboard reads and actions."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_job_search.core.time import utc_now_iso
from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.paths import JOB_ROOT

RUNTIME_DIR = JOB_ROOT / "runtime" / "dashboard-runs"
ACTION_HISTORY_JSONL = RUNTIME_DIR / "dashboard-action-history.jsonl"
RUN_HISTORY_LIMIT = 5


def _load_json(path: Path) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _lock_path(runtime_dir: Path) -> Path:
    return runtime_dir / "dashboard-action.lock"


def _active_run(runtime_dir: Path) -> dict[str, Any] | None:
    lock = _lock_path(runtime_dir)
    data = _load_json(lock)
    if isinstance(data, dict):
        return data
    if lock.exists():
        return {"error": "malformed_lock", "path": str(lock)}
    return None


def _recent_runs(
    runtime_dir: Path,
    limit: int = RUN_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    if not runtime_dir.exists():
        return []
    runs: list[dict[str, Any]] = []
    for path in sorted(
        runtime_dir.glob("run-*.json"),
        key=lambda item: item.name,
        reverse=True,
    ):
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
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


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
            value = json.loads(text)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(value, dict):
            rows.append(value)
        else:
            malformed += 1
    return rows, malformed


def write_jsonl_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
        encoding="utf-8",
    )
    temporary.replace(path)


def read_dashboard_action_history(
    path: Path = ACTION_HISTORY_JSONL,
) -> list[dict[str, Any]]:
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
    canonical = _profile_history_key(profile_url)
    record = {
        "action_type": action_type,
        "profile_url": canonical,
        "timestamp": utc_now_iso(),
        "old_status": old_status,
        "new_status": new_status,
        "operator_source": operator_source,
    }
    action_history_path.parent.mkdir(parents=True, exist_ok=True)
    with action_history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_recruiter_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _row_status(row: dict[str, Any]) -> str:
    return f"{str(row.get('send_tier') or '')}:{str(row.get('decision') or '')}"
