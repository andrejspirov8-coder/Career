"""Read-only liveness checks for opportunity queue ranking.

The checker only reads public job pages. It does not submit forms, accept
consent prompts, log in, upload files, or interact with LinkedIn.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from career_job_search.opportunities.models import (
    Opportunity,
    OpportunityLiveStatus,
    OpportunitySourceKind,
    OpportunityStatus,
    next_action_for_opportunity,
    utc_now_iso,
)

DEFAULT_LIVE_CHECK_TIMEOUT_SECONDS = 6
DEFAULT_LIVE_CHECK_MAX_CANDIDATES = 12
DEFAULT_LIVE_CHECK_WORKERS = 4
CHECKABLE_SOURCE_KINDS = {
    OpportunitySourceKind.MANUAL_INBOX,
    OpportunitySourceKind.JOB_ALERT,
    OpportunitySourceKind.JOB_BOARD,
    OpportunitySourceKind.WEB_SEARCH,
}

CLOSED_TERMS = (
    "this job has expired",
    "job has expired",
    "job ad is not active",
    "job advert is not active",
    "you cant candidate to this job ad anymore",
    "you can't candidate to this job ad anymore",
    "you cannot apply to this job ad anymore",
    "no longer accepting applications",
    "no longer available",
    "position has been filled",
    "job is closed",
    "vacancy is closed",
    "vacancy has expired",
    "posting has expired",
    "application period has ended",
    "negalioja",
    "skelbimas neaktyvus",
    "cv siųsti nebegalite",
    "cv siusti nebegalite",
    "nebegalite pretenduoti",
    "nebegalite kandidatuoti",
    "nedirba",
    "недійсно",
    "оголошення про роботу не активне",
    "недействительно",
    "объявление о работе неактивно",
    "вы не можете больше претендовать",
)

APPLY_TERMS = (
    "apply for this job",
    "apply now",
    "apply",
    "application",
    "send cv",
    "submit application",
    "kandidatuoti",
    "pateikti kandidat",
    "siųsti cv",
    "siusti cv",
    "pretenduoti",
    "aplikuoti",
)

BLOCKED_TERMS = (
    "access denied",
    "forbidden",
    "enable javascript",
    "captcha",
    "checking your browser",
)

LOGIN_WALL_TERMS = (
    "authwall",
    "sign in to linkedin",
    "join linkedin",
    "verify you're human",
    "security verification",
    "unusual activity",
)

STOP_TOKENS = {
    "and",
    "the",
    "for",
    "with",
    "job",
    "jobs",
    "role",
    "specialist",
    "manager",
    "lead",
    "senior",
    "sr",
    "uab",
    "lithuania",
    "vilnius",
    "remote",
    "europe",
}


@dataclass(frozen=True)
class LiveCheckResult:
    status: OpportunityLiveStatus
    method: str
    note: str


def html_to_visible_text(markup: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", markup or "")
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def classify_live_page(
    *,
    title: str,
    company: str,
    visible_text: str,
    status_code: int = 200,
) -> LiveCheckResult:
    text = re.sub(r"\s+", " ", visible_text or "").strip()
    lowered = text.lower()
    if status_code in {404, 410}:
        return LiveCheckResult("closed", "public_page", f"http_{status_code}")
    if status_code in {401, 403, 429}:
        return LiveCheckResult("unverified", "public_page", f"http_{status_code}")
    if not text:
        return LiveCheckResult("unverified", "public_page", "empty_or_script_rendered_page")
    if any(term in lowered for term in CLOSED_TERMS):
        return LiveCheckResult("closed", "public_page", "closed_or_inactive_text_found")
    if any(term in lowered for term in LOGIN_WALL_TERMS):
        return LiveCheckResult("unverified", "public_page", "login_or_access_wall")
    if len(text) < 80:
        return LiveCheckResult("unverified", "public_page", "empty_or_script_rendered_page")

    matches_role = _matches_text(title, lowered)
    matches_company = _matches_text(company, lowered)
    has_apply_signal = any(term in lowered for term in APPLY_TERMS)

    if has_apply_signal and (matches_role or matches_company):
        return LiveCheckResult("live", "public_page", "matching_role_with_apply_signal")
    if any(term in lowered for term in BLOCKED_TERMS):
        return LiveCheckResult("unverified", "public_page", "blocked_or_challenge_page")
    if not matches_role and not matches_company:
        return LiveCheckResult("unverified", "public_page", "page_does_not_match_role")
    return LiveCheckResult("unverified", "public_page", "matching_role_without_apply_signal")


def fetch_public_page_text(
    url: str,
    *,
    timeout: int = DEFAULT_LIVE_CHECK_TIMEOUT_SECONDS,
    max_bytes: int = 500_000,
) -> tuple[int, str]:
    request = Request(  # noqa: S310
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "career-job-search-live-check/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read(max_bytes)
            return int(response.status), html_to_visible_text(raw.decode(charset, errors="replace"))
    except HTTPError as exc:
        try:
            raw = exc.read(max_bytes)
            text = html_to_visible_text(raw.decode("utf-8", errors="replace"))
        except Exception:
            text = ""
        return int(exc.code), text


def check_opportunity_liveness(
    opportunity: Opportunity,
    *,
    timeout: int = DEFAULT_LIVE_CHECK_TIMEOUT_SECONDS,
) -> LiveCheckResult:
    if not opportunity.source_url:
        return LiveCheckResult("unverified", "public_page", "missing_source_url")
    try:
        status_code, text = fetch_public_page_text(opportunity.source_url, timeout=timeout)
    except (TimeoutError, URLError, OSError) as exc:
        return LiveCheckResult("unverified", "public_page", f"fetch_failed:{type(exc).__name__}")
    return classify_live_page(
        title=opportunity.title,
        company=opportunity.company,
        visible_text=text,
        status_code=status_code,
    )


def apply_daily_live_gate(
    opportunities: list[Opportunity],
    *,
    fresh_dedupe_keys: Iterable[str],
    max_page_checks: int = DEFAULT_LIVE_CHECK_MAX_CANDIDATES,
    timeout: int = DEFAULT_LIVE_CHECK_TIMEOUT_SECONDS,
    workers: int = DEFAULT_LIVE_CHECK_WORKERS,
) -> list[Opportunity]:
    """Stamp live evidence before dashboard queues are built."""

    now = utc_now_iso()
    fresh = set(fresh_dedupe_keys)
    by_id = {row.opportunity_id: row for row in opportunities}

    for row in opportunities:
        if row.source_kind == OpportunitySourceKind.ATS and row.dedupe_key in fresh:
            _stamp_live_result(
                row,
                LiveCheckResult(
                    "live",
                    "ats_feed",
                    "rediscovered_from_public_ats_feed",
                ),
                checked_at=now,
            )

    candidates = _page_check_candidates(opportunities, max_page_checks=max_page_checks)
    if not candidates:
        return opportunities

    worker_count = max(1, min(workers, len(candidates)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(check_opportunity_liveness, row, timeout=timeout): row.opportunity_id
            for row in candidates
        }
        for future in as_completed(futures):
            row = by_id[futures[future]]
            try:
                result = future.result()
            except Exception as exc:  # Defensive: keep queue running on one bad site.
                result = LiveCheckResult(
                    "unverified",
                    "public_page",
                    f"check_failed:{type(exc).__name__}",
                )
            _stamp_live_result(row, result, checked_at=now)

    return opportunities


def _page_check_candidates(
    opportunities: list[Opportunity],
    *,
    max_page_checks: int,
) -> list[Opportunity]:
    rows = [
        row
        for row in opportunities
        if row.source_kind in CHECKABLE_SOURCE_KINDS
        and row.source_url
        and row.status
        not in {
            OpportunityStatus.APPLIED,
            OpportunityStatus.SKIPPED,
            OpportunityStatus.EXPIRED,
            OpportunityStatus.FOLLOW_UP,
        }
        and _match_score(row) >= 8
        and not (
            row.source_kind == OpportunitySourceKind.JOB_ALERT
            and row.live_status == "live"
        )
        and not (
            row.source_kind == OpportunitySourceKind.JOB_BOARD
            and row.live_status == "live"
            and row.live_check_method == "linkedin_browser"
        )
    ]
    return sorted(rows, key=_match_score, reverse=True)[:max_page_checks]


def _stamp_live_result(
    opportunity: Opportunity,
    result: LiveCheckResult,
    *,
    checked_at: str,
) -> None:
    opportunity.live_status = result.status
    opportunity.live_checked_at = checked_at
    opportunity.live_check_method = result.method
    opportunity.live_check_note = result.note

    flags = [flag for flag in opportunity.evidence.risk_flags if flag not in {"likely_closed", "needs_live_verification"}]
    if result.status == "closed":
        opportunity.likely_closed = True
        opportunity.status = OpportunityStatus.EXPIRED
        flags.append("likely_closed")
    elif result.status == "unverified":
        opportunity.likely_closed = False
        if opportunity.status not in {OpportunityStatus.APPLIED, OpportunityStatus.SKIPPED}:
            opportunity.status = OpportunityStatus.REVIEW
        flags.append("needs_live_verification")
    elif result.status == "live":
        opportunity.likely_closed = False

    opportunity.evidence.risk_flags = list(dict.fromkeys(flags))
    opportunity.next_action = next_action_for_opportunity(opportunity)


def _match_score(opportunity: Opportunity) -> float:
    if not opportunity.match:
        return 0.0
    return float(opportunity.match.fit_score or opportunity.match.score or 0.0)


def _matches_text(value: str, lowered_text: str) -> bool:
    normalized = (value or "").lower().strip()
    if not normalized:
        return False
    if normalized in lowered_text:
        return True
    tokens = [
        token
        for token in re.findall(r"[\wąčęėįšųūžĄČĘĖĮŠŲŪŽ]+", normalized.lower())
        if len(token) >= 4 and token not in STOP_TOKENS
    ]
    if not tokens:
        return False
    hits = sum(1 for token in tokens if token in lowered_text)
    required = max(1, min(3, (len(tokens) + 1) // 2))
    return hits >= required
