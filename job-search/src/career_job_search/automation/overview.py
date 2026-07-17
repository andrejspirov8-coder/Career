"""Automation worker health and dashboard overview summaries."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_job_search.automation.queue import (
    ACTIVE_STATUSES,
    DEFAULT_AUTOMATION_DB,
    RUN_KIND_DAILY_SEARCH,
    RUN_KINDS,
    SOURCE_STALE_HOURS,
    TERMINAL_STATUSES,
    WORKER_ONLINE_SECONDS,
    connect,
    get_settings,
    init_db,
    list_runs,
    utc_now,
    utc_now_iso,
)


def _latest_worker(*, db_path: Path | str = DEFAULT_AUTOMATION_DB) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("""
            SELECT * FROM automation_workers
            ORDER BY heartbeat_at DESC
            LIMIT 1
            """).fetchone()
    if row is None:
        return {"online": False, "status": "not_started"}
    heartbeat = datetime.fromisoformat(str(row["heartbeat_at"]))
    age_seconds = max(0, int((utc_now() - heartbeat).total_seconds()))
    return {
        "online": str(row["status"]) == "running"
        and age_seconds <= WORKER_ONLINE_SECONDS,
        "status": str(row["status"]),
        "mode": str(row["mode"]),
        "started_at": str(row["started_at"]),
        "heartbeat_at": str(row["heartbeat_at"]),
        "age_seconds": age_seconds,
    }


def _source_health(
    runs: list[dict[str, Any]], *, now: datetime | None = None
) -> dict[str, Any]:
    """Summarize the latest source check without exposing raw private errors."""

    latest = next(
        (
            run
            for run in runs
            if run.get("kind") == RUN_KIND_DAILY_SEARCH
            and isinstance(run.get("result"), dict)
            and isinstance(run["result"].get("source_results"), list)
        ),
        None,
    )
    if latest is None:
        return {
            "overall_status": "not_run",
            "last_checked_at": None,
            "age_hours": None,
            "sources": [],
            "message": "Run the daily search once to check each source.",
        }

    checked_text = str(
        latest.get("finished_at")
        or latest.get("started_at")
        or latest.get("requested_at")
        or ""
    )
    try:
        checked_at = datetime.fromisoformat(checked_text)
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=UTC)
        age_hours = max(
            0,
            int(
                ((now or utc_now()) - checked_at.astimezone(UTC)).total_seconds()
                // 3600
            ),
        )
    except ValueError:
        age_hours = None

    result = latest["result"]
    issue_messages = {
        str(issue.get("source") or "unknown"): str(issue.get("message") or "")[:240]
        for issue in result.get("source_issues", [])
        if isinstance(issue, dict)
    }
    sources: list[dict[str, Any]] = []
    for raw in result.get("source_results", []):
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source") or "unknown")[:100]
        raw_status = str(raw.get("status") or "unknown")[:40]
        complete = bool(raw.get("complete"))
        if raw_status == "failed":
            status = "failed"
            message = (
                issue_messages.get(source)
                or "This source failed during the latest run."
            )
        elif raw_status == "monitor_only" or not complete:
            status = "attention"
            message = (
                issue_messages.get(source) or "Coverage was limited in the latest run."
            )
        elif age_hours is not None and age_hours >= SOURCE_STALE_HOURS:
            status = "stale"
            message = "The last successful check is older than 36 hours."
        else:
            status = "healthy"
            item_count = max(0, int(raw.get("item_count") or 0))
            message = f"Checked successfully; {item_count} item{'s' if item_count != 1 else ''} found."
        sources.append(
            {
                "source": source,
                "status": status,
                "raw_status": raw_status,
                "complete": complete,
                "item_count": max(0, int(raw.get("item_count") or 0)),
                "duration_ms": max(0, int(raw.get("duration_ms") or 0)),
                "message": message,
            }
        )

    priorities = {"failed": 4, "attention": 3, "stale": 2, "healthy": 1}
    overall = max(
        (row["status"] for row in sources),
        key=lambda status: priorities[status],
        default="not_run",
    )
    messages = {
        "failed": "At least one source failed. Other successful results were kept.",
        "attention": "At least one source returned limited coverage.",
        "stale": "Source health is stale. Run today's search to refresh it.",
        "healthy": "All checked sources completed normally.",
        "not_run": "No source details were returned by the latest run.",
    }
    return {
        "overall_status": overall,
        "last_checked_at": checked_text or None,
        "age_hours": age_hours,
        "sources": sources,
        "message": messages[overall],
    }


def build_overview(
    *,
    db_path: Path | str = DEFAULT_AUTOMATION_DB,
    limit: int = 30,
) -> dict[str, Any]:
    init_db(db_path)
    runs = list_runs(db_path=db_path, limit=limit)
    counts = {status: 0 for status in (*ACTIVE_STATUSES, *TERMINAL_STATUSES)}
    with connect(db_path) as con:
        for row in con.execute(
            "SELECT status, COUNT(*) AS count FROM automation_runs GROUP BY status"
        ).fetchall():
            counts[str(row["status"])] = int(row["count"])
    return {
        "schema": "career_automation_overview_v1",
        "generated_at": utc_now_iso(),
        "settings": get_settings(db_path=db_path),
        "worker": _latest_worker(db_path=db_path),
        "counts": counts,
        "active_runs": [run for run in runs if run["status"] in ACTIVE_STATUSES],
        "recent_runs": runs,
        "source_health": _source_health(runs),
        "available_actions": list(RUN_KINDS),
        "safety": {
            "scheduled_linkedin_enabled": False,
            "live_linkedin_dispatch_enabled": False,
            "message": (
                "Scheduled searches use inbox, company, and ATS sources only. "
                "LinkedIn review remains manual in the recruiter workspace."
            ),
        },
    }
