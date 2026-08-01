"""Local job-file inbox opportunity source."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from career_job_search.cvs.matching import JOB_ROOT, parse_job_file
from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityEvidence,
    OpportunitySourceKind,
)
from career_job_search.opportunities.normalization import infer_remote_policy

DEFAULT_INBOX_JOBS = JOB_ROOT / "inbox" / "jobs"


def infer_location(parsed: dict[str, Any]) -> str:
    text = " ".join(
        str(parsed.get(key) or "") for key in ("title", "company", "body", "source")
    ).lower()
    if "vilnius" in text:
        return "Vilnius"
    if "lithuania" in text or "lietuva" in text:
        return "Lithuania"
    if "baltic" in text or "baltics" in text:
        return "Baltics"
    if "remote" in text:
        return "Remote"
    return ""


def opportunity_from_job_file(path: Path) -> Opportunity:
    raw = path.read_text(encoding="utf-8")
    parsed = parse_job_file(raw, job_file_path=str(path.resolve()))
    source = str(parsed.get("source") or "manual_inbox") or "manual_inbox"
    body = str(parsed.get("body") or "")
    title = str(parsed.get("title") or "")
    company = str(parsed.get("company") or "")
    source_url = str(parsed.get("url") or "")
    location = infer_location(parsed)
    return Opportunity(
        source=source,
        source_kind=OpportunitySourceKind.MANUAL_INBOX,
        source_url=source_url,
        title=title,
        company=company,
        location=location,
        remote_policy=infer_remote_policy(body),
        description=body,
        evidence=OpportunityEvidence(
            source_facts=[f"inbox:{path.name}"],
            company_facts=[company] if company else [],
            role_facts=[title] if title else [],
            location_facts=[location] if location else [],
            confidence=0.75,
        ),
    )


def discover_inbox_opportunities(config: dict[str, Any]) -> list[Opportunity]:
    sources = (config.get("opportunities") or {}).get("sources") or {}
    block = sources.get("inbox") or {}
    if not isinstance(block, dict) or not bool(block.get("enabled", True)):
        return []
    inbox = Path(str(block.get("path") or DEFAULT_INBOX_JOBS))
    if not inbox.exists():
        return []
    exclude_patterns = [
        str(item).lower()
        for item in block.get("exclude_name_patterns", ["smoke", "test"])
        if str(item).strip()
    ]
    return [
        opportunity_from_job_file(path)
        for path in sorted(inbox.glob("*.job.txt"))
        if not _is_excluded_inbox_job(path, exclude_patterns)
    ]


def _is_excluded_inbox_job(path: Path, exclude_patterns: list[str]) -> bool:
    name = path.name.lower()
    if name.startswith("."):
        return True
    return any(pattern in name for pattern in exclude_patterns)
