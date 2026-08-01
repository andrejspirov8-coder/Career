"""Bridge a safe recruiter session queue into the dashboard review workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.paths import SESSION_STATE_JSON
from career_job_search.recruiters.dashboard_storage import (
    _load_json,
    read_jsonl_records,
    write_jsonl_records,
)

SESSION_SCHEMA = "recruiter_session_state_v1"


def resolve_session_state_path(
    action_plan_path: Path,
    session_state_path: Path | None,
) -> Path:
    """Use the action plan's sibling session file unless explicitly overridden."""
    if session_state_path is not None:
        return session_state_path
    return action_plan_path.with_name(SESSION_STATE_JSON.name)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _persona_and_risks(row: dict[str, Any]) -> tuple[str, list[str]]:
    headline = str(row.get("headline") or "")
    headline_lower = headline.lower()
    persona = str(row.get("persona") or "").strip()
    risks = _string_list(row.get("risk_flags"))

    recruiter_terms = (
        "recruiter",
        "talent acquisition",
        "talent partner",
        "people partner",
        "human resources",
        " hr ",
    )
    manager_terms = ("manager", "lead", "head", "director", "chief", "owner")
    if not persona:
        padded_headline = f" {headline_lower} "
        if any(term in padded_headline for term in recruiter_terms):
            persona = "recruiter_hr"
        elif any(term in headline_lower for term in manager_terms):
            persona = "hiring_manager"
        else:
            persona = "potential_hiring_contact"
            risks.append("hiring_authority_unverified")

    if not bool(row.get("target_company_verified")):
        risks.append("target_company_unverified")
    if "out of office" in headline_lower or "ooo" in headline_lower:
        risks.append("out_of_office")
    return persona, list(dict.fromkeys(risks))


def session_queue_rows(session_state_path: Path) -> list[dict[str, Any]]:
    """Convert a dispatchable session queue into manual-review dashboard rows."""
    document = _load_json(session_state_path)
    if not isinstance(document, dict) or document.get("schema") != SESSION_SCHEMA:
        return []
    queue = document.get("queue")
    if not isinstance(queue, list):
        return []

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in queue:
        if not isinstance(raw, dict):
            continue
        profile_url = lis.canonical_profile_url(str(raw.get("profile_url") or ""))
        if not profile_url or profile_url in seen:
            continue
        seen.add(profile_url)
        persona, risk_flags = _persona_and_risks(raw)
        variant = str(
            raw.get("variant_slug_best") or raw.get("search_variant_slug") or ""
        )
        target_company = str(raw.get("target_company") or "")
        target_verified = bool(raw.get("target_company_verified"))
        target_role = str(raw.get("target_role_title") or "")
        signals = _string_list(raw.get("top_signals"))
        if target_verified:
            signals.append("verified_hiring_company")
        if target_role:
            signals.append(target_role)

        rows.append(
            {
                "profile_url": profile_url,
                "name": str(raw.get("name") or ""),
                "headline": str(raw.get("headline") or ""),
                "company": str(raw.get("company") or target_company),
                "location": str(raw.get("location") or ""),
                "persona": persona,
                "cv_variant": variant,
                "variant_slug": variant,
                "rank_score": raw.get("rank_score") or raw.get("primary_score"),
                "primary_score": raw.get("primary_score"),
                "profile_confidence": raw.get("profile_confidence"),
                "send_tier": "queue_review",
                "decision": "review",
                "risk_flags": risk_flags,
                "note": str(
                    raw.get("note_live_full") or raw.get("note_preview_trim") or ""
                ),
                "note_reason": str(raw.get("note_reason") or "verified_session_queue"),
                "source_backend": str(
                    raw.get("source_backend") or "linkedin_session_queue"
                ),
                "top_signals": list(dict.fromkeys(signals)),
                "target_company": target_company,
                "target_opportunity_id": str(raw.get("target_opportunity_id") or ""),
                "target_role_title": target_role,
                "target_company_verified": target_verified,
                "session_generated_at": str(document.get("generated_at") or ""),
            }
        )
    return rows


def merge_session_queue_rows(
    action_rows: list[dict[str, Any]],
    session_state_path: Path,
) -> tuple[list[dict[str, Any]], int]:
    """Append session-only rows while preserving explicit dashboard decisions."""
    merged = list(action_rows)
    existing = {
        canonical
        for row in action_rows
        if (canonical := lis.canonical_profile_url(str(row.get("profile_url") or "")))
    }
    added = 0
    for row in session_queue_rows(session_state_path):
        profile_url = str(row["profile_url"])
        if profile_url in existing:
            continue
        existing.add(profile_url)
        merged.append(row)
        added += 1
    return merged, added


def materialize_session_profiles(
    profile_urls: list[str],
    *,
    action_plan_path: Path,
    session_state_path: Path | None = None,
) -> list[str]:
    """Persist requested session-only rows before a dashboard mutation."""
    wanted = {
        canonical
        for value in profile_urls
        if (canonical := lis.canonical_profile_url(value))
    }
    if not wanted:
        return []

    action_rows, _malformed = read_jsonl_records(action_plan_path)
    existing = {
        canonical
        for row in action_rows
        if (canonical := lis.canonical_profile_url(str(row.get("profile_url") or "")))
    }
    session_path = resolve_session_state_path(action_plan_path, session_state_path)
    added: list[str] = []
    for row in session_queue_rows(session_path):
        profile_url = str(row["profile_url"])
        if profile_url not in wanted or profile_url in existing:
            continue
        action_rows.append(row)
        existing.add(profile_url)
        added.append(profile_url)
    if added:
        write_jsonl_records(action_plan_path, action_rows)
    return added
