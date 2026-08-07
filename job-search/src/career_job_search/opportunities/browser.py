"""Normalize read-only browser-extracted job listings.

The scheduled automation can use the user's already authenticated Chrome
session, then pass only structured listing fields into this module. This keeps
credentials and browser state out of the local SQLite pipeline while reusing
the same matching, liveness, and delivery rules as every other source.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, TextIO

from career_job_search.opportunities.live import classify_live_page
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
    OpportunityStatus,
    normalise_url,
)
from career_job_search.opportunities.normalization import (
    canonical_linkedin_job_url as _canonical_linkedin_job_url,
)
from career_job_search.opportunities.normalization import (
    infer_remote_policy,
    linkedin_job_id_from_url,
)

MAX_STORED_DESCRIPTION_CHARS = 6000
BROWSER_LIVE_WINDOW_HOURS = 24


class BrowserJobPayloadError(ValueError):
    """Raised when a browser listing payload is incomplete or unsafe."""


def load_browser_job_payloads(stream: TextIO) -> list[dict[str, Any]]:
    """Load one structured browser listing per NDJSON line."""

    payloads: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(stream, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BrowserJobPayloadError(
                f"Invalid browser JSON on line {line_number}: {exc.msg}"
            ) from exc
        if not isinstance(payload, dict):
            raise BrowserJobPayloadError(
                f"Invalid browser JSON on line {line_number}: expected an object"
            )
        payloads.append(payload)
    return payloads


def opportunity_from_browser_job(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
) -> Opportunity:
    """Build one current LinkedIn opportunity from a browser observation."""

    source = str(payload.get("source") or "linkedin").strip().casefold()
    if source != "linkedin":
        raise BrowserJobPayloadError("only source=linkedin is supported")

    raw_url = str(payload.get("url") or payload.get("source_url") or "").strip()
    source_url = canonical_linkedin_job_url(raw_url)
    if not source_url:
        raise BrowserJobPayloadError("url must be a LinkedIn /jobs/view/ listing")

    title = _clean(payload.get("title"))
    company = _clean(payload.get("company"))
    if not title or not company:
        raise BrowserJobPayloadError("title and company are required")

    captured_at = str(payload.get("captured_at") or "").strip()
    if not captured_at:
        raise BrowserJobPayloadError("captured_at is required")
    captured = _parse_datetime(captured_at, field_name="captured_at")
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)
    clock = clock.astimezone(UTC)

    detail_text = _clean(payload.get("detail_text") or payload.get("description"))
    detail_live_text = _clean(payload.get("detail_live_text") or detail_text)
    snippet = _clean(payload.get("snippet"))
    description = detail_text or snippet or f"{title} at {company}."
    detail_read = bool(payload.get("detail_read", False))
    detail_verified = detail_read and bool(detail_text)
    current = abs(clock - captured) <= timedelta(hours=BROWSER_LIVE_WINDOW_HOURS)
    risk_flags = [] if current else ["needs_live_verification"]
    source_facts = ["chrome:linkedin_jobs_search"]
    if detail_read:
        source_facts.append("chrome:linkedin_job_detail")

    location = _clean(payload.get("detail_location") or payload.get("location"))
    salary = _clean(
        payload.get("detail_salary")
        or payload.get("salary")
        or payload.get("salary_text")
    )
    live_status = "live" if current else "unverified"
    live_note = (
        "browser_job_card_and_detail" if detail_read else "browser_job_card_only"
    )
    likely_closed = False
    status = OpportunityStatus.NEW
    if current and detail_verified:
        detail_result = classify_live_page(
            title=title,
            company=company,
            visible_text=detail_live_text,
        )
        live_status = detail_result.status
        live_note = f"browser_detail_{detail_result.note}"
        if detail_result.status == "closed":
            likely_closed = True
            status = OpportunityStatus.EXPIRED
            risk_flags.append("likely_closed")
        elif detail_result.status == "unverified":
            risk_flags.append("needs_live_verification")

    row = Opportunity(
        source="linkedin",
        source_kind=OpportunitySourceKind.JOB_BOARD,
        native_source_id=linkedin_job_id_from_url(source_url),
        source_url=source_url,
        title=title,
        company=company,
        location=location,
        remote_policy=infer_remote_policy(f"{location} {snippet} {detail_text}"),
        description=description[:MAX_STORED_DESCRIPTION_CHARS],
        salary_text=salary,
        discovered_at=captured.isoformat(),
        live_status=live_status,
        live_checked_at=captured.isoformat(),
        live_check_method="linkedin_browser",
        live_check_note=live_note if current else "browser_capture_is_old",
        likely_closed=likely_closed,
        status=status,
        evidence=OpportunityEvidence(
            source_facts=source_facts,
            company_facts=[company],
            role_facts=[title],
            location_facts=[location] if location else [],
            risk_flags=risk_flags,
            confidence=0.85 if detail_read else 0.8,
        ),
    )
    return row


job_id_from_url = linkedin_job_id_from_url


def canonical_linkedin_job_url(url: str) -> str:
    return _canonical_linkedin_job_url(url, normalize_url=normalise_url)


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BrowserJobPayloadError(f"{field_name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()
