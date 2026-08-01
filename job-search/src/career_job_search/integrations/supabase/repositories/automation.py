"""Supabase-backed automation run repository."""

from __future__ import annotations

from typing import Any

from career_job_search.integrations.supabase.client import get_client


def enqueue_run(
    run_id: str,
    kind: str,
    trigger_source: str,
    scheduled_for: str | None = None,
    unique_key: str | None = None,
) -> dict[str, Any]:
    client = get_client()
    result = (
        client.table("automation_runs")
        .insert(
            {
                "run_id": run_id,
                "kind": kind,
                "status": "queued",
                "trigger_source": trigger_source,
                "scheduled_for": scheduled_for,
                "unique_key": unique_key,
            }
        )
        .execute()
    )
    return result.data[0] if result.data else {}


def dequeue_next() -> dict[str, Any] | None:
    client = get_client()
    result = (
        client.table("automation_runs")
        .select("*")
        .eq("status", "queued")
        .order("requested_at")
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def update_status(
    run_id: str,
    status: str,
    result_json: dict[str, Any] | None = None,
    error: str = "",
) -> None:
    client = get_client()
    update: dict[str, Any] = {"status": status}
    if result_json is not None:
        update["result_json"] = result_json
    if error:
        update["error"] = error
    if status in ("running",):
        update["started_at"] = "now()"
    if status in ("succeeded", "failed", "cancelled"):
        update["finished_at"] = "now()"
    client.table("automation_runs").update(update).eq("run_id", run_id).execute()
