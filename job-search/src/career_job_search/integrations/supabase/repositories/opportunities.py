"""Supabase-backed opportunity repository.

Replaces ``opportunities/repository_db.py`` when ``get_storage().is_remote``.
"""

from __future__ import annotations

from typing import Any

from career_job_search.integrations.supabase.client import get_client


def upsert_opportunity(
    opportunity_id: str,
    dedupe_key: str,
    source_kind: str,
    title: str,
    company: str,
    location: str,
    status: str,
    data_json: dict[str, Any],
) -> dict[str, Any]:
    client = get_client()
    result = (
        client.table("opportunities")
        .upsert(
            {
                "opportunity_id": opportunity_id,
                "dedupe_key": dedupe_key,
                "source_kind": source_kind,
                "title": title,
                "company": company,
                "location": location,
                "status": status,
                "data_json": data_json,
                "updated_at": "now()",
            },
            on_conflict="dedupe_key",
        )
        .execute()
    )
    return result.data[0] if result.data else {}


def get_opportunity(opportunity_id: str) -> dict[str, Any] | None:
    client = get_client()
    result = (
        client.table("opportunities")
        .select("*")
        .eq("opportunity_id", opportunity_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def list_opportunities(status: str | None = None) -> list[dict[str, Any]]:
    client = get_client()
    query = client.table("opportunities").select("*")
    if status:
        query = query.eq("status", status)
    result = query.order("updated_at", desc=True).execute()
    return result.data


def record_action(
    opportunity_id: str,
    action_type: str,
    old_status: str | None = None,
    new_status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    client = get_client()
    result = (
        client.table("opportunity_actions")
        .insert(
            {
                "opportunity_id": opportunity_id,
                "action_type": action_type,
                "old_status": old_status,
                "new_status": new_status,
                "metadata_json": metadata or {},
            }
        )
        .execute()
    )
    return result.data[0]["id"] if result.data else 0


def count_by_status() -> dict[str, int]:
    client = get_client()
    result = client.rpc("count_opportunities_by_status").execute()
    counts: dict[str, int] = {}
    for row in result.data or []:
        counts[str(row["status"])] = int(row["count"])
    return counts
