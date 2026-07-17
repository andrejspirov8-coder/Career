"""Normalize official job-alert email payloads into local opportunities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TextIO
from urllib.parse import urlsplit

from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
)
from career_job_search.opportunities.normalization import infer_remote_policy

ALERT_LIVE_WINDOW_HOURS = 48
MAX_STORED_SNIPPET_CHARS = 1000


class AlertPayloadError(ValueError):
    """Raised when the automation provides an invalid alert payload."""


@dataclass
class AlertImportResult:
    opportunities: list[Opportunity] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    messages_processed: int = 0


_SOURCE_NAMES = {
    "cvbankas": "cvbankas",
    "cv bankas": "cvbankas",
    "cv-online": "cvonline",
    "cv online": "cvonline",
    "cvonline": "cvonline",
    "work in lithuania": "workinlithuania",
    "workinlithuania": "workinlithuania",
    "linkedin": "linkedin",
    "linkedin jobs": "linkedin",
    "linkedin job alert": "linkedin",
}


def load_alert_payloads(stream: TextIO) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(stream, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AlertPayloadError(
                f"Invalid alert JSON on line {line_number}: {exc.msg}"
            ) from exc
        if not isinstance(payload, dict):
            raise AlertPayloadError(
                f"Invalid alert JSON on line {line_number}: expected an object"
            )
        payloads.append(payload)
    return payloads


def opportunities_from_alert(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
) -> AlertImportResult:
    message_id = _required_text(payload, "message_id")
    received_at = _required_text(payload, "received_at")
    source_hint = _normalise_source(str(payload.get("source") or ""))
    subject = str(payload.get("subject") or "").strip()
    body = str(payload.get("body") or "")
    links = payload.get("links") or []
    if not isinstance(links, list):
        raise AlertPayloadError("links must be a list")

    received = _parse_datetime(received_at, field_name="received_at")
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)

    result = AlertImportResult(messages_processed=1)
    for index, raw_link in enumerate(links, start=1):
        link = {"url": raw_link} if isinstance(raw_link, str) else raw_link
        if not isinstance(link, dict):
            result.errors.append(f"link {index}: expected a URL or object")
            continue
        url = str(link.get("url") or "").strip()
        source = _source_for_url(url)
        if not source:
            result.errors.append(f"link {index}: unsupported job URL")
            continue
        if source_hint and source_hint != source:
            result.errors.append(f"link {index}: source does not match the job URL")
            continue

        title, company = _title_and_company(link, subject)
        location = str(link.get("location") or "").strip() or _infer_location(body)
        salary = str(link.get("salary") or "").strip() or _infer_salary(body)
        if not title or not company:
            result.errors.append(f"link {index}: title and company are required")
            continue

        snippet = _stored_snippet(
            str(link.get("snippet") or link.get("description") or ""),
            title=title,
            company=company,
            location=location,
        )
        is_recent = _is_recent(received, clock)
        flags = [] if is_recent else ["needs_live_verification"]
        native_id = _native_id(source, url) or f"{message_id}:{index}"
        remote_policy = infer_remote_policy(
            " ".join(
                [
                    location,
                    str(link.get("work_mode") or ""),
                    snippet,
                ]
            )
        ).title()
        result.opportunities.append(
            Opportunity(
                source=source,
                source_kind=OpportunitySourceKind.JOB_ALERT,
                native_source_id=native_id,
                source_url=url,
                title=title,
                company=company,
                location=location,
                remote_policy=remote_policy,
                description=snippet,
                salary_text=salary,
                discovered_at=received.isoformat(),
                live_status="live" if is_recent else "unverified",
                live_checked_at=received.isoformat(),
                live_check_method="official_job_alert",
                live_check_note=(
                    "official_alert_received_within_48_hours"
                    if is_recent
                    else "official_alert_older_than_48_hours"
                ),
                evidence=OpportunityEvidence(
                    source_facts=[
                        f"gmail:{message_id}",
                        f"official_alert:{source}",
                    ],
                    company_facts=[company],
                    role_facts=[title],
                    location_facts=[location] if location else [],
                    risk_flags=flags,
                    confidence=0.75 if is_recent else 0.55,
                ),
            )
        )
    return result


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise AlertPayloadError(f"{key} is required")
    return value


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AlertPayloadError(f"{field_name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalise_source(value: str) -> str:
    return _SOURCE_NAMES.get(" ".join(value.casefold().split()), "")


def _source_for_url(url: str) -> str:
    host = urlsplit(url).netloc.casefold().removeprefix("www.")
    if host in {"cvbankas.lt", "en.cvbankas.lt", "ru.cvbankas.lt"}:
        return "cvbankas"
    if host in {"cvonline.lt", "cv-online.lt", "www2.cvonline.lt"}:
        return "cvonline"
    if host in {"jobs.workinlithuania.com", "workinlithuania.com"}:
        return "workinlithuania"
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return "linkedin"
    return ""


def _native_id(source: str, url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    patterns = {
        "cvbankas": r"/1-(\d+)$",
        "cvonline": r"/vacancy/([^/]+)$",
        "workinlithuania": r"/job/([^/]+)$",
        "linkedin": r"/jobs/view/(\d+)$",
    }
    match = re.search(patterns[source], path, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _title_and_company(
    link: dict[str, Any],
    subject: str,
) -> tuple[str, str]:
    title = str(link.get("title") or "").strip()
    company = str(link.get("company") or "").strip()
    if title and company:
        return title, company
    if "@" in subject:
        fallback_title, fallback_company = subject.rsplit("@", 1)
        return title or fallback_title.strip(), company or fallback_company.strip()
    return title or subject, company


def _infer_location(body: str) -> str:
    for raw_line in body.splitlines():
        line = " ".join(raw_line.split()).strip()
        lowered = line.casefold()
        if line and any(
            token in lowered
            for token in ("vilnius", "vilniaus", "vilniuje", "remote", "lithuania")
        ):
            return line[:240]
    return ""


def _infer_salary(body: str) -> str:
    for raw_line in body.splitlines():
        line = " ".join(raw_line.split()).strip()
        if re.search(r"(?:€|\beur\b).*\d|\d.*(?:€|\beur\b)", line, re.IGNORECASE):
            return line[:160]
    return ""


def _stored_snippet(
    raw: str,
    *,
    title: str,
    company: str,
    location: str,
) -> str:
    text = " ".join(raw.split()).strip()
    if not text:
        text = " - ".join(part for part in (title, company, location) if part)
    return text[:MAX_STORED_SNIPPET_CHARS]


def _is_recent(received: datetime, now: datetime) -> bool:
    age_hours = (now.astimezone(UTC) - received.astimezone(UTC)).total_seconds() / 3600
    return 0 <= age_hours <= ALERT_LIVE_WINDOW_HOURS
