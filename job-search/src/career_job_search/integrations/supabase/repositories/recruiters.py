"""Supabase-backed recruiter repository.

Replaces ``recruiters/repository.py`` when ``get_storage().is_remote``.
"""

from __future__ import annotations

from typing import Any

from career_job_search.integrations.supabase.client import get_client


def ensure_profile(
    profile_url: str,
    name: str = "",
    title: str = "",
    company: str = "",
    location: str = "",
    source: str = "",
) -> str:
    client = get_client()
    client.table("recruiter_profiles").upsert(
        {
            "profile_url": profile_url,
            "name": name,
            "title": title,
            "company": company,
            "location": location,
            "source": source,
            "updated_at": "now()",
        },
        on_conflict="profile_url",
    ).execute()
    return profile_url


def record_decision(
    profile_url: str,
    run_id: str,
    status: str,
    note: str = "",
    score: float | None = None,
    tier: str = "",
    reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    client = get_client()
    nh = _compute_note_hash(note)
    approved_at = "now()" if status == "approved" else None
    sent_at = "now()" if status == "sent" else None
    client.table("recruiter_decisions").upsert(
        {
            "profile_url": profile_url,
            "run_id": run_id,
            "status": status,
            "note": note,
            "note_hash": nh,
            "score": score,
            "tier": tier,
            "reason": reason,
            "metadata_json": metadata or {},
            "approved_at": approved_at,
            "sent_at": sent_at,
        },
        on_conflict="profile_url,note_hash,status",
    ).execute()
    return nh


def _compute_note_hash(note: str) -> str:
    from hashlib import sha256

    return sha256((note or "").strip().encode("utf-8")).hexdigest()


def approval_check(
    profile_url: str,
    note: str,
) -> dict[str, Any]:
    client = get_client()
    canon = _canonical(profile_url)
    nh = _compute_note_hash(note) if note else ""
    if not canon or not nh:
        return {"approved": False, "reason": "missing_params"}
    sent = (
        client.table("recruiter_decisions")
        .select("id")
        .eq("profile_url", canon)
        .eq("status", "sent")
        .limit(1)
        .execute()
    )
    if sent.data:
        return {"approved": False, "reason": "already_sent"}
    approved = (
        client.table("recruiter_decisions")
        .select("id")
        .eq("profile_url", canon)
        .eq("note_hash", nh)
        .eq("status", "approved")
        .limit(1)
        .execute()
    )
    if not approved.data:
        return {"approved": False, "reason": "missing_matching_approval"}
    return {"approved": True, "reason": "approved"}


def _canonical(url: str) -> str:
    from career_job_search.integrations.linkedin.selectors import canonical_profile_url

    return canonical_profile_url(url) or ""


def count_by_status() -> dict[str, int]:
    client = get_client()
    result = client.rpc("count_recruiter_decisions_by_status").execute()
    counts: dict[str, int] = {}
    for row in result.data or []:
        counts[str(row["status"])] = int(row["count"])
    return counts


def sent_profile_urls_on_local_date(day: str | None = None) -> list[str]:
    client = get_client()
    from datetime import UTC, datetime

    target = day or datetime.now(UTC).date().isoformat()
    result = (
        client.table("recruiter_decisions")
        .select("profile_url")
        .eq("status", "sent")
        .gte("sent_at", f"{target}T00:00:00Z")
        .lte("sent_at", f"{target}T23:59:59Z")
        .execute()
    )
    return [row["profile_url"] for row in result.data]
