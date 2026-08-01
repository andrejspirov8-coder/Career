"""Prioritise recruiter discovery using reviewed job opportunities.

The opportunity pipeline remains the source of truth for which companies are
currently relevant. This module only produces read-only recruiter search
targets; it cannot browse LinkedIn or send outreach.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from career_job_search.opportunities.alerts import ALERT_LIVE_WINDOW_HOURS
from career_job_search.opportunities.browser import BROWSER_LIVE_WINDOW_HOURS
from career_job_search.opportunities.models import Opportunity, OpportunityStatus
from career_job_search.opportunities.repository import (
    DEFAULT_OPPORTUNITY_DB,
    list_opportunities,
)

DEFAULT_MAX_COMPANIES = 6
DEFAULT_MIN_FIT_SCORE = 8.0
DEFAULT_QUERIES_PER_COMPANY = 2
MAX_CONFIGURED_COMPANIES = 20

_ACTIVE_STATUSES = {
    OpportunityStatus.MATCHED,
    OpportunityStatus.REVIEW,
    OpportunityStatus.APPLY_READY,
    OpportunityStatus.APPLIED,
    OpportunityStatus.FOLLOW_UP,
}
_HUMAN_ADVANCED_STATUSES = {
    OpportunityStatus.APPLY_READY,
    OpportunityStatus.APPLIED,
    OpportunityStatus.FOLLOW_UP,
}
_STATUS_PRIORITY = {
    OpportunityStatus.FOLLOW_UP: 50,
    OpportunityStatus.APPLIED: 45,
    OpportunityStatus.APPLY_READY: 35,
    OpportunityStatus.REVIEW: 25,
    OpportunityStatus.MATCHED: 20,
}
_ELIGIBLE_LOCATIONS = {
    "eligible_vilnius",
    "eligible_lt_remote",
    "eligible_eu_remote",
}
_BLOCKING_RISK_FLAGS = {
    "duplicate",
    "language_requirement_risk",
    "likely_closed",
    "location_ineligible",
    "low_cv_score",
    "needs_live_verification",
    "possible_duplicate",
    "possible_scam",
    "remote_eligibility_unverified",
    "role_family_mismatch",
    "third_party_recruiter_only",
    "visa_location_risk",
    "vague_role",
    "watchlist_only",
    "weak_location_fit",
}
_COMPANY_NOISE_TOKENS = {
    "ab",
    "and",
    "as",
    "co",
    "company",
    "companies",
    "corp",
    "corporation",
    "group",
    "groups",
    "holding",
    "holdings",
    "inc",
    "limited",
    "lithuania",
    "lietuva",
    "llc",
    "ltd",
    "of",
    "oy",
    "plc",
    "srl",
    "the",
    "uab",
    "vsi",
}


@dataclass(frozen=True)
class OpportunityTargetSettings:
    enabled: bool = True
    max_companies: int = DEFAULT_MAX_COMPANIES
    min_fit_score: float = DEFAULT_MIN_FIT_SCORE
    queries_per_company: int = DEFAULT_QUERIES_PER_COMPANY


@dataclass(frozen=True)
class OpportunityRecruiterTarget:
    opportunity_id: str
    company: str
    title: str
    location: str
    cv_variant: str
    role_track: str
    fit_score: float
    status: str
    live_status: str
    live_checked_at: str
    source_url: str
    priority_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OpportunityRecruiterQuery:
    cv_variant: str
    query: str
    search_intent: str
    target_company: str
    target_opportunity_id: str
    target_role_title: str


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _bounded_float(value: Any, *, default: float, minimum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def opportunity_target_settings(full_cfg: dict[str, Any]) -> OpportunityTargetSettings:
    web_discovery = full_cfg.get("web_discovery") or {}
    raw = (
        web_discovery.get("opportunity_targets")
        if isinstance(web_discovery, dict)
        else {}
    )
    block = raw if isinstance(raw, dict) else {}
    return OpportunityTargetSettings(
        enabled=bool(block.get("enabled", True)),
        max_companies=_bounded_int(
            block.get("max_companies"),
            default=DEFAULT_MAX_COMPANIES,
            minimum=1,
            maximum=MAX_CONFIGURED_COMPANIES,
        ),
        min_fit_score=_bounded_float(
            block.get("min_fit_score"),
            default=DEFAULT_MIN_FIT_SCORE,
            minimum=0.0,
        ),
        queries_per_company=_bounded_int(
            block.get("queries_per_company"),
            default=DEFAULT_QUERIES_PER_COMPANY,
            minimum=1,
            maximum=2,
        ),
    )


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _is_fresh_live(opportunity: Opportunity, *, now: datetime) -> bool:
    if opportunity.live_status != "live":
        return False
    checked_at = _parse_timestamp(opportunity.live_checked_at)
    if checked_at is None:
        return False
    window_hours = (
        ALERT_LIVE_WINDOW_HOURS
        if opportunity.live_check_method == "official_job_alert"
        else BROWSER_LIVE_WINDOW_HOURS
    )
    age = now - checked_at
    return timedelta(0) <= age <= timedelta(hours=window_hours)


def _fit_score(opportunity: Opportunity) -> float:
    if opportunity.match is None:
        return 0.0
    return max(float(opportunity.match.fit_score), float(opportunity.match.score))


def _candidate_target(
    opportunity: Opportunity,
    *,
    min_fit_score: float,
    now: datetime,
) -> OpportunityRecruiterTarget | None:
    if opportunity.status not in _ACTIVE_STATUSES:
        return None
    if opportunity.live_status == "closed" or opportunity.likely_closed:
        return None
    if not opportunity.company.strip() or not opportunity.title.strip():
        return None
    if opportunity.title.strip().casefold() == "company watchlist":
        return None
    if opportunity.location_eligibility not in _ELIGIBLE_LOCATIONS:
        return None
    if _BLOCKING_RISK_FLAGS.intersection(opportunity.evidence.risk_flags):
        return None
    if opportunity.match is None or not opportunity.match.best_variant.strip():
        return None

    fit_score = _fit_score(opportunity)
    if fit_score < min_fit_score:
        return None

    fresh_live = _is_fresh_live(opportunity, now=now)
    if not fresh_live and opportunity.status not in _HUMAN_ADVANCED_STATUSES:
        return None

    reason = (
        "fresh_live_match"
        if fresh_live
        else f"human_advanced:{opportunity.status.value}"
    )
    return OpportunityRecruiterTarget(
        opportunity_id=opportunity.opportunity_id,
        company=opportunity.company.strip(),
        title=opportunity.title.strip(),
        location=opportunity.location.strip(),
        cv_variant=opportunity.match.best_variant.strip(),
        role_track=opportunity.match.role_track.strip(),
        fit_score=round(fit_score, 2),
        status=opportunity.status.value,
        live_status=opportunity.live_status,
        live_checked_at=opportunity.live_checked_at,
        source_url=opportunity.source_url,
        priority_reason=reason,
    )


def _target_priority(target: OpportunityRecruiterTarget) -> tuple[int, int, float, str]:
    status = OpportunityStatus(target.status)
    return (
        _STATUS_PRIORITY[status],
        int(target.priority_reason == "fresh_live_match"),
        target.fit_score,
        target.live_checked_at,
    )


def build_opportunity_targets(
    opportunities: list[Opportunity],
    *,
    max_companies: int = DEFAULT_MAX_COMPANIES,
    min_fit_score: float = DEFAULT_MIN_FIT_SCORE,
    now: datetime | None = None,
) -> list[OpportunityRecruiterTarget]:
    """Return one deterministic, high-quality target per hiring company."""

    clock = (now or datetime.now(UTC)).astimezone(UTC)
    best_by_company: dict[str, OpportunityRecruiterTarget] = {}
    for opportunity in opportunities:
        target = _candidate_target(
            opportunity,
            min_fit_score=min_fit_score,
            now=clock,
        )
        if target is None:
            continue
        company_key = _company_identity_key(target.company)
        if not company_key:
            continue
        existing = best_by_company.get(company_key)
        if existing is None or _target_priority(target) > _target_priority(existing):
            best_by_company[company_key] = target

    return sorted(
        best_by_company.values(),
        key=_target_priority,
        reverse=True,
    )[: max(0, max_companies)]


def load_opportunity_targets(
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
    max_companies: int = DEFAULT_MAX_COMPANIES,
    min_fit_score: float = DEFAULT_MIN_FIT_SCORE,
    now: datetime | None = None,
) -> list[OpportunityRecruiterTarget]:
    path = Path(db_path)
    if not path.is_file():
        return []
    return build_opportunity_targets(
        list_opportunities(db_path=path),
        max_companies=max_companies,
        min_fit_score=min_fit_score,
        now=now,
    )


def safe_load_opportunity_targets(
    *,
    db_path: Path | str = DEFAULT_OPPORTUNITY_DB,
    settings: OpportunityTargetSettings | None = None,
    now: datetime | None = None,
) -> tuple[list[OpportunityRecruiterTarget], str]:
    selected = settings or OpportunityTargetSettings()
    if not selected.enabled:
        return [], ""
    try:
        return (
            load_opportunity_targets(
                db_path=db_path,
                max_companies=selected.max_companies,
                min_fit_score=selected.min_fit_score,
                now=now,
            ),
            "",
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        return [], f"opportunity_targets_unavailable:{type(exc).__name__}"


def _quoted_search_phrase(value: str) -> str:
    cleaned = re.sub(r"[_/]+", " ", value.replace('"', " "))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return f'"{cleaned[:120]}"'


def _company_tokens(value: str) -> list[str]:
    normalised = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in normalised if not unicodedata.combining(char))
    return re.findall(r"[a-z0-9]+", ascii_text)


def _company_identity_tokens(value: str) -> list[str]:
    all_tokens = _company_tokens(value)
    meaningful = [token for token in all_tokens if token not in _COMPANY_NOISE_TOKENS]
    return meaningful or all_tokens


def _company_identity_key(value: str) -> str:
    return "".join(_company_identity_tokens(value))


def _company_search_clause(value: str) -> str:
    exact = _quoted_search_phrase(value)
    brand = _quoted_search_phrase(" ".join(_company_identity_tokens(value)))
    if exact.casefold() == brand.casefold():
        return exact
    return f"({exact} OR {brand})"


def company_name_matches_text(company: str, *evidence: str) -> bool:
    """Return whether visible profile evidence names the selected company."""

    company_tokens = _company_identity_tokens(company)
    if not company_tokens:
        return False

    evidence_tokens = _company_tokens(" ".join(str(item or "") for item in evidence))
    evidence_set = set(evidence_tokens)
    if all(token in evidence_set for token in company_tokens):
        return True

    compact_company = "".join(company_tokens)
    compact_evidence = "".join(evidence_tokens)
    return len(compact_company) >= 4 and compact_company in compact_evidence


def opportunity_target_query_rows(
    targets: list[OpportunityRecruiterTarget],
    *,
    queries_per_company: int = DEFAULT_QUERIES_PER_COMPANY,
) -> list[OpportunityRecruiterQuery]:
    """Return company-first recruiter queries with their opportunity context."""

    query_count = max(1, min(2, queries_per_company))
    rows: list[OpportunityRecruiterQuery] = []
    for query_index in range(query_count):
        for target in targets:
            company = _company_search_clause(target.company)
            role = _quoted_search_phrase(target.role_track or target.title)
            company_queries = [
                (
                    f"{company} AND "
                    '(recruiter OR "talent acquisition" OR "people partner" '
                    'OR "HR business partner")',
                    "recruiter",
                ),
                (
                    f'{company} AND ("hiring manager" OR head OR director) '
                    f"AND ({role} OR operations OR process)",
                    "hiring_leader",
                ),
            ]
            query, search_intent = company_queries[query_index]
            rows.append(
                OpportunityRecruiterQuery(
                    cv_variant=target.cv_variant,
                    query=query,
                    search_intent=search_intent,
                    target_company=target.company,
                    target_opportunity_id=target.opportunity_id,
                    target_role_title=target.title,
                )
            )
    return rows


def opportunity_target_queries(
    targets: list[OpportunityRecruiterTarget],
    *,
    queries_per_company: int = DEFAULT_QUERIES_PER_COMPANY,
) -> list[tuple[str, str]]:
    """Return CV-aware public search queries, with no browser side effects."""

    return [
        (row.cv_variant, row.query)
        for row in opportunity_target_query_rows(
            targets,
            queries_per_company=queries_per_company,
        )
    ]
