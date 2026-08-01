"""Supabase-backed notification repository."""

from __future__ import annotations

from typing import Any

from career_job_search.integrations.supabase.client import get_client


def upsert_notification(
    notification_id: str,
    scope: str,
    category: str,
    kind: str,
    priority: str,
    lifecycle: str,
    title: str,
    body: str,
    href: str = "",
) -> dict[str, Any]:
    client = get_client()
    result = (
        client.table("notifications")
        .upsert(
            {
                "notification_id": notification_id,
                "scope": scope,
                "category": category,
                "kind": kind,
                "priority": priority,
                "lifecycle": lifecycle,
                "title": title,
                "body": body,
                "href": href,
            },
            on_conflict="notification_id",
        )
        .execute()
    )
    return result.data[0] if result.data else {}


def list_notifications(
    limit: int = 50,
    unread_first: bool = True,
) -> list[dict[str, Any]]:
    client = get_client()
    query = client.table("notifications").select("*")
    if unread_first:
        query = query.order("read_at", nulls_first=True)
    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data


def mark_read(notification_id: str) -> None:
    client = get_client()
    client.table("notifications").update(
        {"read_at": "now()"}
    ).eq("notification_id", notification_id).execute()


def count_unread() -> int:
    client = get_client()
    result = (
        client.table("notifications")
        .select("id", count="exact")
        .is_("read_at", "null")
        .execute()
    )
    return result.count or 0
