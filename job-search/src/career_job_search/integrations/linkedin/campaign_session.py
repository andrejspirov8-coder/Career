"""Browser-session helpers for LinkedIn recruiter campaign discovery."""

from __future__ import annotations

import argparse
import random
import re
import sys
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.browser import (
    LinkedInAutomatorBase,
    PlaywrightLinkedInAutomator,
)
from career_job_search.integrations.linkedin.campaign_config import (
    dwell_navigation,
    jitter_sleep,
    people_search_url,
    read_retry_connect_queue,
)
from career_job_search.integrations.linkedin.paths import PROFILE_DIR, RECRUITERS_CSV
from career_job_search.recruiters.log import append_recruiter_row, recruiter_row_partial
from career_job_search.recruiters.opportunity_targets import (
    opportunity_target_query_rows,
    opportunity_target_settings,
    safe_load_opportunity_targets,
)
from career_job_search.recruiters.search import merged_queries_for_variant


def sample_automation_html(
    automation: LinkedInAutomatorBase, cap: int = 170_000
) -> str:
    try:
        return automation.html_sample(cap)
    except Exception:
        return ""


def sample_html(page: Any, cap: int = 170_000) -> str:
    try:
        return page.content()[:cap]
    except Exception:
        return ""


def assert_not_blocked(page: Any, *, scan_html: bool = True) -> str | None:
    """Playwright-page helper retained for callers that still hold a raw page."""
    return assert_blocked_automation(
        PlaywrightLinkedInAutomator(page, limits={}),
        scan_login_locators=True,
        scan_html=scan_html,
    )


def assert_blocked_automation(
    automation: LinkedInAutomatorBase,
    *,
    scan_login_locators: bool = True,
    scan_html: bool = True,
) -> str | None:
    blocker = lis.detect_blockers(
        url=automation.current_url(),
        html_sample=sample_automation_html(
            automation, cap=380_000 if scan_html else 12_000
        ),
        scan_html=scan_html,
    )
    if blocker:
        return blocker
    if not scan_login_locators:
        return None
    page = getattr(automation, "page", None)
    if page is not None:
        try:
            for sel in lis.LOGIN_FIELD_SELECTORS:
                try:
                    if page.locator(sel).first.is_visible(timeout=450):
                        return "login_wall_visible"
                except Exception:  # noqa: S112
                    continue
        except Exception:  # noqa: S110
            pass
        return None
    try:
        pwd = int(
            automation.evaluate(
                "document.querySelectorAll('input[type=password]').length"
            )
            or 0
        )
        email = int(
            automation.evaluate("document.querySelectorAll('input[type=email]').length")
            or 0
        )
        text_login = automation.html_sample(500_000).lower()
        if (
            pwd > 0
            or email > 3
            or ("sign in" in text_login and "password" in text_login)
        ):
            return "login_wall_visible"
    except Exception:
        return None
    return None


LOGIN_BLOCKERS = frozenset(
    {
        "checkpoint_or_auth_url",
        "login_wall_visible",
        "suspected_challenge_or_review_page",
    }
)


def wait_for_manual_login(
    page: Any,
    *,
    base_url: str,
    headed: bool,
    timeout_seconds: int = 300,
) -> bool:
    automation = PlaywrightLinkedInAutomator(page, limits={})
    return wait_for_manual_login_automation(
        automation,
        base_url=base_url,
        headed=headed,
        timeout_seconds=timeout_seconds,
        dwell_limits={
            "dwell_after_navigate_seconds_min": 1,
            "dwell_after_navigate_seconds_max": 2,
        },
    )


def wait_for_manual_login_automation(
    automation: LinkedInAutomatorBase,
    *,
    base_url: str,
    headed: bool,
    timeout_seconds: int = 300,
    dwell_limits: dict[str, Any] | None = None,
) -> bool:
    """Pause in headed mode so the user can sign in or pass a checkpoint."""
    if not headed:
        return False

    print(
        "LinkedIn wants sign-in or verification — use the automation Chrome window "
        f"(profile: {PROFILE_DIR}; waiting up to {timeout_seconds // 60} min). "
        "Signing in via Cursor's browser panel does not count.",
        flush=True,
    )

    deadline = time.time() + timeout_seconds
    feed_url = f"{base_url.rstrip('/')}/feed/"
    dwell = dwell_limits or {
        "dwell_after_navigate_seconds_min": 1,
        "dwell_after_navigate_seconds_max": 2,
    }

    while time.time() < deadline:
        jitter_sleep(4.0, 7.0)
        try:
            automation.goto(feed_url)
        except Exception:  # noqa: S110
            pass
        dwell_navigation(dwell)
        blocker = assert_blocked_automation(automation)
        if blocker is None:
            print("Login check passed — continuing.", flush=True)
            return True
        if blocker not in LOGIN_BLOCKERS:
            print(f"Still blocked ({blocker}); not a login screen.", flush=True)
            return False

    print("Timed out waiting for login.", flush=True)
    return False


def _search_result_cards(html: str) -> dict[str, str]:
    """Best-effort map of canonical profile URL -> visible search-card text."""
    cards: dict[str, str] = {}
    if not html:
        return cards
    for raw in re.findall(r'href="(https://[^"]*?/in/[^"?#]+)"', html):
        canon = lis.canonical_profile_url(raw.split("?", 1)[0])
        if not canon:
            continue
        idx = html.find(raw)
        if idx < 0:
            continue
        window = html[max(0, idx - 4000) : idx + 4000]
        text = re.sub(r"<[^>]+>", " ", window)
        text = re.sub(r"\s+", " ", text).strip()
        if text and (canon not in cards or len(text) > len(cards[canon])):
            cards[canon] = text[:2000]
    return cards


def harvest_profile_urls(
    automation: LinkedInAutomatorBase,
    *,
    max_new: int,
    seed_seen: set[str],
    cfg_limits: dict[str, Any],
    evidence_by_url: dict[str, str] | None = None,
) -> list[str]:
    rounds = int(cfg_limits.get("scroll_result_pages_max", 6))
    scroll_px = int(cfg_limits.get("scroll_step_px", 900))
    collected: list[str] = []
    dup_guard: set[str] = set(seed_seen)

    for _ in range(rounds):
        hrefs = automation.eval_on_selector_all_hrefs('a[href*="/in/"]')

        cards: dict[str, str] = {}
        if evidence_by_url is not None:
            cards = _search_result_cards(sample_automation_html(automation))

        for raw in hrefs:
            canon = lis.canonical_profile_url(raw.split("?", 1)[0])
            if not canon:
                continue
            if canon in dup_guard:
                continue
            dup_guard.add(canon)
            collected.append(canon)
            if evidence_by_url is not None:
                evidence_by_url[canon] = cards.get(canon, "")
            if len(collected) >= max_new:
                return collected[:max_new]

        try:
            automation.mouse_wheel(scroll_px)
        except Exception:
            try:
                automation.evaluate(
                    f"(function(){{window.scrollBy(0, {int(scroll_px)});}})()"
                )
            except Exception:  # noqa: S110
                pass
        jitter_sleep(1.6, 2.8)

    return collected[:max_new]


def browser_was_closed(exc: BaseException) -> bool:
    """True when Playwright lost the page because the user closed Chrome."""
    if type(exc).__name__ == "TargetClosedError":
        return True
    msg = str(exc).lower()
    return "has been closed" in msg or "target page, context or browser" in msg


_BROWSER_CLOSED_MSG = (
    "Browser window closed during the run — leave the headed Chrome window open "
    'until the bot prints "LinkedIn recruiter run finished."'
)

# Gate hits worth a one-line log when directors / ops leaders pass (not plain "recruiter").
_LEADERSHIP_GATE_LOG_TERMS = frozenset(
    {
        "area manager",
        "regional manager",
        "district manager",
        "cluster manager",
        "store director",
        "retail director",
        "operations director",
        "director of operations",
        "director of retail",
        "director of stores",
        "general manager",
        "hiring manager",
        "head of people",
        "head of hr",
        "head of human resources",
        "chief people officer",
        "country manager retail",
        "parduotuvės direktor",
        "mažmeninės prekybos direktor",
        "regiono vadov",
    }
)


def automation_goto_or_closed(automation: LinkedInAutomatorBase, url: str) -> bool:
    """Navigate; return False if the user closed Chrome (no exception)."""
    try:
        automation.goto(url)
        return True
    except Exception as exc:
        if browser_was_closed(exc):
            print(_BROWSER_CLOSED_MSG, flush=True)
            return False
        err_msg = str(exc).lower()
        if (
            "err_aborted" in err_msg
            or "frame was detached" in err_msg
            or "navigation interrupted" in err_msg
        ):
            print(
                "Navigation was aborted or redirected on-the-fly (likely challenge intercept). Checking page state...",
                flush=True,
            )
            return True
        raise


def automation_evaluate_or_closed(
    automation: LinkedInAutomatorBase, js_expression: str
) -> Any | None:
    """Run page JS; return None if Chrome was closed (one retry on transient TargetClosedError)."""
    last_exc: BaseException | None = None
    for attempt in range(2):
        try:
            return automation.evaluate(js_expression)
        except Exception as exc:
            last_exc = exc
            if browser_was_closed(exc):
                if attempt == 0:
                    time.sleep(0.6)
                    continue
                print(_BROWSER_CLOSED_MSG, flush=True)
                return None
            raise
    if last_exc is not None:
        raise last_exc
    return None


def automation_try_invite_or_closed(
    automation: LinkedInAutomatorBase,
    *,
    note_text: str,
    run_logs_dir: Path,
    profile_tag: str,
    jitter_sleep: Callable[[float, float], None],
) -> tuple[bool | None, str, str]:
    """
    Send connection invite. Returns (None, msg, path) when the browser closed mid-run.
    Retries once on TargetClosedError (tab crash / user closed window).
    """
    last_exc: BaseException | None = None
    for attempt in range(2):
        try:
            return automation.try_send_invitation(
                note_text=note_text,
                run_logs_dir=run_logs_dir,
                profile_tag=profile_tag,
                jitter_sleep=jitter_sleep,
            )
        except Exception as exc:
            last_exc = exc
            if browser_was_closed(exc):
                if attempt == 0:
                    time.sleep(0.8)
                    continue
                print(_BROWSER_CLOSED_MSG, flush=True)
                return None, "browser_closed_mid_invite", ""
            raise
    if last_exc is not None:
        raise last_exc
    return False, "invite_failed_unknown", ""


def idle_feed_automation(
    automation: LinkedInAutomatorBase, *, base_url: str, limits: dict[str, Any]
) -> None:
    lo = float(limits.get("idle_browse_seconds_min", 60))
    hi = float(limits.get("idle_browse_seconds_max", 120))
    feed = f"{base_url.rstrip('/')}/feed/"
    try:
        automation.goto(feed)
    except Exception:
        return
    jitter_sleep(lo, hi)
    try:
        automation.mouse_wheel(random.randint(320, 1100))  # noqa: S311
    except Exception:  # noqa: S110
        pass
    jitter_sleep(2.0, 5.5)


def looks_pending_automation(automation: LinkedInAutomatorBase) -> bool:
    page = getattr(automation, "page", None)
    if page is not None:
        locators = (
            page.locator('[aria-label*="Pending"]').first,
            page.get_by_role("button", name=re.compile(r"pending", re.I)).first,
        )
        for loc in locators:
            try:
                if loc.is_visible(timeout=500):
                    return True
            except Exception:  # noqa: S112
                continue
    blob = sample_automation_html(automation, 280_000).lower()
    return bool(blob and ("pending invitation" in blob or "\npending\n" in blob))


def looks_pending_connection(page: Any) -> bool:
    return looks_pending_automation(PlaywrightLinkedInAutomator(page, limits={}))


def try_send_invitation(
    page: Any, *, note_text: str, run_logs_dir: Path, profile_tag: str
) -> tuple[bool, str, str]:
    """Delegate to playwright connect flow with shared jitter pacing."""
    from career_job_search.integrations.linkedin.connect_flow import (
        playwright_try_send_invitation,
    )

    return playwright_try_send_invitation(
        page,
        note_text=note_text,
        run_logs_dir=run_logs_dir,
        profile_tag=profile_tag,
        jitter_fn=jitter_sleep,
    )


def _warmup_and_maybe_login(
    automation: LinkedInAutomatorBase,
    *,
    base_url: str,
    headed: bool,
    limits: dict[str, Any],
    shutdown_browser: Callable[[], None],
) -> str | None:
    """Warm up feed; optionally wait for headed login. Return blocker string or None."""
    if not automation_goto_or_closed(automation, f"{base_url}/feed/"):
        shutdown_browser()
        return "browser_closed"
    dwell_navigation(limits)
    block = assert_blocked_automation(automation, scan_html=False)

    if block and block in LOGIN_BLOCKERS:
        if not wait_for_manual_login_automation(
            automation,
            base_url=base_url,
            headed=headed,
            timeout_seconds=int(limits.get("login_timeout_seconds", 300)),
        ):
            append_recruiter_row(
                recruiter_row_partial(
                    date_iso=date.today().isoformat(),
                    profile_url=automation.current_url()[:390],
                    name="__meta__warmup",
                    confidence=block,
                    status="blocked",
                    skip_reason=block,
                )
            )
            shutdown_browser()
            return block
        block = assert_blocked_automation(automation)

    if block:
        append_recruiter_row(
            recruiter_row_partial(
                date_iso=date.today().isoformat(),
                profile_url=automation.current_url()[:390],
                name="__meta__warmup",
                confidence=block,
                status="blocked",
                skip_reason=block,
            )
        )
        shutdown_browser()
        return block
    return None


_SEARCH_EVIDENCE_RELATIONSHIP_RE = re.compile(
    r"\b(mutual connections?|followers?|connections?)\b", re.IGNORECASE
)


def current_company_evidence_from_search_result(search_result_text: str) -> str:
    """Return visible lines naming the recruiter's current company/headline."""
    lines = [ln.strip() for ln in re.split(r"\n+", search_result_text) if ln.strip()]
    kept: list[str] = []
    for line in lines[:12]:
        if line.startswith("Past:"):
            continue
        if _SEARCH_EVIDENCE_RELATIONSHIP_RE.search(line):
            continue
        kept.append(line)
    return "\n".join(kept)[:1000]


def headline_from_search_result(search_result_text: str) -> str:
    """Extract the search-card headline line (title, company) from card text."""
    lines = [ln.strip() for ln in re.split(r"\n+", search_result_text) if ln.strip()]
    for index, line in enumerate(lines[:10]):
        if index == 0:
            continue
        if re.match(r"^•?\s*(1st|2nd|3rd)\b", line, re.IGNORECASE):
            continue
        if re.match(r"^(Current|Past):", line):
            continue
        if _SEARCH_EVIDENCE_RELATIONSHIP_RE.search(line):
            continue
        if line.strip() in {"Follow", "Connect", "Message"}:
            continue
        if line.count(",") < 1:
            continue
        if re.search(r"\b(Vilnius|Kaunas|Lithuania|Lietuva)\b", line, re.IGNORECASE):
            continue
        if len(re.findall(r"[^\W\d_]", line)) < 3:
            continue
        return line[:500]
    return ""


def _unpack_queue_item(
    item: tuple[str, ...],
) -> tuple[str, str, str, str, str, str, str]:
    """(profile_url, variant_slug, search_intent, company, opp_id, title, evidence)."""
    url = item[0]
    variant = item[1] if len(item) > 1 else ""
    intent = item[2] if len(item) > 2 else ""
    company = item[3] if len(item) > 3 else ""
    opp_id = item[4] if len(item) > 4 else ""
    title = item[5] if len(item) > 5 else ""
    evidence = item[6] if len(item) > 6 else ""
    return (url, variant, intent, company, opp_id, title, evidence)


def collect_discovery_queue_for_session(
    automation: LinkedInAutomatorBase,
    *,
    raw_cfg: dict[str, Any],
    args: argparse.Namespace,
    scoring_cap: int,
    limits: dict[str, Any],
    search: dict[str, Any],
    base_url: str,
    shutdown_browser: Callable[[], None],
    seen_profiles: set[str],
) -> list[tuple[str, str, str, str, str, str, str]] | None:
    """Harvest People-search URLs (company targets, retries, generic ordering).

    Queue rows are 7-tuples ``(profile_url, variant_slug, search_intent, company,
    opportunity_id, title, current_company_evidence)``. ``None`` = fatal blocker.
    """
    queries_map = search.get("queries_by_variant") or {}
    if not isinstance(queries_map, dict) or not queries_map:
        return []

    target_rows: list[Any] = []
    targets: list[Any] = []
    settings = opportunity_target_settings(raw_cfg)
    if settings.enabled:
        targets, _err = safe_load_opportunity_targets(settings=settings)
        target_rows = opportunity_target_query_rows(
            targets,
            queries_per_company=settings.queries_per_company,
        )

    variants = list(queries_map.keys())

    if args.variant_filter:
        if args.variant_filter not in variants:
            print(
                f"Unknown variant slug {args.variant_filter!r}; known: {variants}",
                file=sys.stderr,
            )
            return []
        variants = [args.variant_filter]

    queued: list[tuple[str, str, str, str, str, str, str]] = []
    generic: list[tuple[str, str, str, str, str, str, str]] = []
    local_seen = set(seen_profiles)

    def visit_and_harvest(
        url: str,
        *,
        slug: str,
        ql: str,
        evidence_by_url: dict[str, str] | None,
        max_new: int,
    ) -> list[str] | None:
        if not automation_goto_or_closed(automation, url):
            shutdown_browser()
            return None
        dwell_navigation(limits)
        block2 = assert_blocked_automation(automation, scan_html=False)
        if block2:
            append_recruiter_row(
                recruiter_row_partial(
                    date_iso=date.today().isoformat(),
                    profile_url=automation.current_url()[:390],
                    name="__meta__discovery_blocked",
                    variant_slug=slug,
                    confidence=block2,
                    status="blocked",
                    skip_reason=block2,
                    note_preview=ql[:180],
                )
            )
            shutdown_browser()
            print(f"Halted discovery (variant={slug}): {block2}", flush=True)
            return None
        return harvest_profile_urls(
            automation,
            max_new=max_new,
            seed_seen=local_seen,
            cfg_limits=limits,
            evidence_by_url=evidence_by_url,
        )

    for row in target_rows:
        if len(queued) >= scoring_cap:
            break
        evidence_by_url: dict[str, str] = {}
        url = people_search_url(row.query, base_url)
        new_urls = visit_and_harvest(
            url,
            slug=row.cv_variant,
            ql=row.query,
            evidence_by_url=evidence_by_url,
            max_new=1,
        )
        if new_urls is None:
            return None
        for u in new_urls[:1]:
            evidence = current_company_evidence_from_search_result(
                evidence_by_url.get(u, "")
            )
            queued.append(
                (
                    u,
                    row.cv_variant,
                    row.search_intent,
                    row.target_company,
                    row.target_opportunity_id,
                    row.target_role_title,
                    evidence,
                )
            )
            local_seen.add(u)

    for slug in variants:
        merged = merged_queries_for_variant(raw_cfg, slug)
        if not merged:
            continue
        need = scoring_cap - len(queued) - len(generic)
        if need <= 0:
            break
        for qline, search_intent in merged:
            need_inner = scoring_cap - len(queued) - len(generic)
            if need_inner <= 0:
                break
            ql = str(qline or "").strip()
            if not ql:
                continue

            url = people_search_url(ql, base_url)
            evidence_by_url = {}
            new_urls = visit_and_harvest(
                url,
                slug=slug,
                ql=ql,
                evidence_by_url=evidence_by_url,
                max_new=max(need_inner * 10, 32),
            )
            if new_urls is None:
                return None

            for u in new_urls:
                if len(queued) + len(generic) >= scoring_cap:
                    break
                evidence = current_company_evidence_from_search_result(
                    evidence_by_url.get(u, "")
                )
                generic.append((u, slug, search_intent, "", "", "", evidence))
                local_seen.add(u)

    retry_first = read_retry_connect_queue(RECRUITERS_CSV)
    pilot_mode = args.max_connections_override is not None

    if retry_first:
        already_queued = {item[0] for item in queued} | {
            item[0] for item in generic
        }
        retry_sevens = [
            (u, v, "", "", "", "", "")
            for u, v in retry_first
            if u not in already_queued
        ]
        queued = queued + retry_sevens + generic
        queued = queued[:scoring_cap]
        print(
            f"Retrying {len(retry_first)} profile(s) with prior Connect failures first.",
            flush=True,
        )
    elif pilot_mode and not getattr(args, "dry_run", False):
        queued = (queued + generic)[: min(len(queued) + len(generic), 8)]
    else:
        queued = queued + generic
        queued = queued[:scoring_cap]

    return queued
