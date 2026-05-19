#!/usr/bin/env python3
"""
LinkedIn recruiter scout: People search → profile scrape → CV match → optional connection invite.

Run from `job-search/`:
  python3 tools/linkedin_recruiter_bot.py --headed --dry-run
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import re
import sys
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

try:
    import yaml
except ModuleNotFoundError as exc:
    yaml = None
    yaml_import_exc = exc
else:
    yaml_import_exc = None

import linkedin_selectors as lis
from linkedin_browser import (
    LinkedInAutomatorBase,
    PlaywrightLinkedInAutomator,
    backend_from_cfg,
    start_browse_ws_session,
)
from linkedin_profile_lock import (
    describe_profile_lock,
    is_profile_in_use_error,
    release_stale_chrome_profile_lock,
)
from matching_lib import TOOLS_DIR
from playwright.sync_api import sync_playwright
from recruiter_linkedin_paths import (
    DEFAULT_LINKEDIN_CONFIG,
    PROFILE_DIR,
    RECRUITERS_CSV,
    RUN_LOGS_DIR,
)
from recruiter_log import (
    append_recruiter_row,
    ensure_recruiter_csv_schema,
    recruiter_row_partial,
)
from recruiter_match import (
    assign_best_tier,
    gate_terms_from_recruiter_cfg,
    match_recruiter_profile,
    matched_hiring_gate_terms,
    prepare_outreach_note_bundle,
    should_send_recruiter_connection,
)
from recruiter_search import merged_queries_for_variant

JOB_ROOT = TOOLS_DIR.parent
DEFAULT_CONFIG = DEFAULT_LINKEDIN_CONFIG

# Playwright channel names that map to browsers installed on the machine.
SUPPORTED_BROWSER_CHANNELS = frozenset(
    {"chrome", "chrome-beta", "msedge", "msedge-beta", "msedge-dev"}
)


def load_config(config_path: Path) -> dict[str, Any]:
    if yaml is None:
        raise SystemExit(f"Need PyYAML: pip install pyyaml ({yaml_import_exc})")
    if not config_path.exists():
        raise SystemExit(f"Missing config file: {config_path}")
    with config_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise SystemExit("Config root must be a mapping")
    return cfg


def cfg_limits(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("limits") or {}


def cfg_matching(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("matching") or {}


def cfg_search(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("search") or {}


def cfg_browser(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("browser") or {}


def cfg_recruiter_matching(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("recruiter_matching") or {}


def accept_rate_from_csv(csv_path: Path) -> float | None:
    sent = 0
    accepted = 0
    if not csv_path.exists():
        return None
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("status") or "").strip() != "sent":
                continue
            sent += 1
            if (row.get("accepted_at") or "").strip():
                accepted += 1
    if sent == 0:
        return None
    return accepted / sent


def effective_daily_invite_cap(
    limits: dict[str, Any], csv_path: Path = RECRUITERS_CSV
) -> int:
    """
    Use the conservative cap until we have enough sent rows and a strong accept rate.

    (Plan: day-cap 8 until accept rate >= 40%.)
    """
    full_cap = int(limits.get("max_connections_per_day", 12))
    low_cap = int(limits.get("max_connections_per_day_low_accept", 8))
    need_rate = float(limits.get("min_accept_rate_for_full_cap", 0.4))
    min_sent = int(limits.get("min_sent_for_accept_rate", 5))
    rate = accept_rate_from_csv(csv_path)
    if rate is None:
        return low_cap
    with csv_path.open(encoding="utf-8", newline="") as f:
        n_sent = sum(
            1
            for row in csv.DictReader(f)
            if (row.get("status") or "").strip() == "sent"
        )
    if n_sent < min_sent:
        return low_cap
    if rate < need_rate:
        return min(full_cap, low_cap)
    return full_cap


def profile_slug_from_url(url: str) -> str:
    m = re.search(r"/in/([^/?#]+)", (url or "").split("?")[0], re.I)
    if m:
        return re.sub(r"[^\w\-]+", "_", m.group(1))[:80]
    return "profile"


def action_delay(limits: dict[str, Any]) -> None:
    lo = float(limits.get("action_delay_seconds_min", 1.5))
    hi = float(limits.get("action_delay_seconds_max", 4.0))
    jitter_sleep(lo, hi)


def between_profiles_delay(limits: dict[str, Any]) -> None:
    median = float(limits.get("between_profiles_seconds_median", 70))
    sigma = float(limits.get("between_profiles_lognormal_sigma", 0.38))
    mu = math.log(max(median, 5.0))
    delay = random.lognormvariate(mu, sigma)
    delay = max(float(limits.get("between_profiles_seconds_floor", 8.0)), delay)
    delay = min(delay, float(limits.get("between_profiles_seconds_cap", 420.0)))
    time.sleep(delay)


def idle_feed_browse(page: Any, *, base_url: str, limits: dict[str, Any]) -> None:
    lo = float(limits.get("idle_browse_seconds_min", 60))
    hi = float(limits.get("idle_browse_seconds_max", 120))
    feed = f"{base_url.rstrip('/')}/feed/"
    try:
        page.goto(feed, wait_until="domcontentloaded")
    except Exception:
        return
    jitter_sleep(lo, hi)
    try:
        page.mouse.wheel(0, random.randint(320, 1100))
    except Exception:
        pass
    jitter_sleep(2.0, 5.5)


def resolve_browser_channel(
    raw_cfg: dict[str, Any], cli_override: str | None
) -> str | None:
    """
    Return a Playwright channel (e.g. chrome) or None for bundled Chromium.

    Default is Google Chrome per linkedin/config.yaml.
    """
    if cli_override is not None:
        token = cli_override.strip().lower()
    else:
        token = str(cfg_browser(raw_cfg).get("channel") or "chrome").strip().lower()

    if token in ("", "chromium", "bundled", "playwright"):
        return None
    if token not in SUPPORTED_BROWSER_CHANNELS:
        allowed = ", ".join(sorted(SUPPORTED_BROWSER_CHANNELS | {"chromium"}))
        raise SystemExit(f"Unknown browser channel {token!r}. Use one of: {allowed}")
    return token


def _profile_in_use_exit_message(*, channel: str | None, exc: BaseException) -> str:
    lock_hint = describe_profile_lock(PROFILE_DIR)
    return (
        "Could not open the automation Chrome profile (another Chrome may be using it).\n"
        f"- Profile folder: {PROFILE_DIR}\n"
        f"- Lock status: {lock_hint}\n"
        "- Sign in inside the bot's Chrome window only — Cursor's Glass/browser panel is a "
        "separate session and will not save login here.\n"
        "- Quit any leftover automation Chrome from a previous run, then retry with --headed.\n"
        "- Run: python3 tools/recruiter_orchestrate.py preflight  (clears stale locks)\n"
        "- Or set browser.channel: chromium in linkedin/config.yaml\n"
        f"Details: {exc}"
    )


def launch_linkedin_browser_context(
    playwright: Any,
    *,
    headed: bool,
    channel: str | None,
) -> Any:
    """Open a persistent browser profile for LinkedIn (Chrome by default)."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    release_stale_chrome_profile_lock(PROFILE_DIR)

    launch_kwargs: dict[str, Any] = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": not headed,
        "locale": "en-GB",
        "viewport": {"width": 1320, "height": 920},
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    label = channel or "playwright-chromium"
    if channel:
        launch_kwargs["channel"] = channel

    def _launch() -> Any:
        return playwright.chromium.launch_persistent_context(**launch_kwargs)

    try:
        return _launch()
    except Exception as exc:
        if is_profile_in_use_error(exc) and release_stale_chrome_profile_lock(
            PROFILE_DIR
        ):
            try:
                return _launch()
            except Exception as retry_exc:
                exc = retry_exc
        if is_profile_in_use_error(exc) or channel == "chrome":
            raise SystemExit(
                _profile_in_use_exit_message(channel=channel, exc=exc)
            ) from exc
        raise SystemExit(f"Could not start browser ({label}): {exc}") from exc


def people_search_url(keywords: str, base_url: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/search/results/people/?keywords={quote_plus(keywords.strip())}&origin=FACETED_SEARCH"


def jitter_sleep(seconds_min: float, seconds_max: float) -> None:
    lo, hi = min(seconds_min, seconds_max), max(seconds_min, seconds_max)
    time.sleep(random.uniform(lo, hi))


def dwell_navigation(limits: dict[str, Any]) -> None:
    lo = float(limits.get("dwell_after_navigate_seconds_min", 2))
    hi = float(limits.get("dwell_after_navigate_seconds_max", 6))
    jitter_sleep(lo, hi)


def read_seen_profile_urls(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    found: set[str] = set()
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            canon = lis.canonical_profile_url(row.get("profile_url") or "")
            if canon:
                found.add(canon)
    return found


def read_retry_connect_queue(csv_path: Path) -> list[tuple[str, str]]:
    """Profiles where Connect failed earlier — try again before new discovery."""
    if not csv_path.exists():
        return []
    retries: list[tuple[str, str]] = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("status") or "") != "skipped_no_connect":
                continue
            canon = lis.canonical_profile_url(row.get("profile_url") or "")
            if not canon:
                continue
            retries.append((canon, (row.get("variant_slug") or "").strip()))
    return retries


def read_skip_revisit_urls(csv_path: Path) -> set[str]:
    """Profile URLs we should not open again (sent, pending, or dry-run only)."""
    if not csv_path.exists():
        return set()
    # Dry-run rows are intentionally revisitable on a live run (only score, no invite sent).
    skip_statuses = frozenset(
        {
            "sent",
            "skipped_pending",
        }
    )
    found: set[str] = set()
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("status") or "") not in skip_statuses:
                continue
            canon = lis.canonical_profile_url(row.get("profile_url") or "")
            if canon:
                found.add(canon)
    return found


def count_status_today(csv_path: Path, status: str = "sent") -> int:
    today = date.today().isoformat()
    if not csv_path.exists():
        return 0
    n = 0
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("date_iso") or "") == today and (
                row.get("status") or ""
            ) == status:
                n += 1
    return n


def planned_invite_for_url(
    planned_invites: dict[str, dict[str, Any]] | None,
    profile_url: str,
) -> dict[str, Any]:
    """Return preapproved note/metadata for a canonical profile URL."""
    if not planned_invites:
        return {}
    canon = lis.canonical_profile_url(profile_url)
    if not canon:
        return {}
    return dict(planned_invites.get(canon) or {})


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
                except Exception:
                    continue
        except Exception:
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
        except Exception:
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


def harvest_profile_urls(
    automation: LinkedInAutomatorBase,
    *,
    max_new: int,
    seed_seen: set[str],
    cfg_limits: dict[str, Any],
) -> list[str]:
    rounds = int(cfg_limits.get("scroll_result_pages_max", 6))
    scroll_px = int(cfg_limits.get("scroll_step_px", 900))
    collected: list[str] = []
    dup_guard: set[str] = set(seed_seen)

    for _ in range(rounds):
        hrefs = automation.eval_on_selector_all_hrefs('a[href*="/in/"]')

        for raw in hrefs:
            canon = lis.canonical_profile_url(raw.split("?", 1)[0])
            if not canon:
                continue
            if canon in dup_guard:
                continue
            dup_guard.add(canon)
            collected.append(canon)
            if len(collected) >= max_new:
                return collected[:max_new]

        try:
            automation.mouse_wheel(scroll_px)
        except Exception:
            try:
                automation.evaluate(
                    f"(function(){{window.scrollBy(0, {int(scroll_px)});}})()"
                )
            except Exception:
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
        automation.mouse_wheel(random.randint(320, 1100))
    except Exception:
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
            except Exception:
                continue
    blob = sample_automation_html(automation, 280_000).lower()
    return bool(blob and ("pending invitation" in blob or "\npending\n" in blob))


def looks_pending_connection(page: Any) -> bool:
    return looks_pending_automation(PlaywrightLinkedInAutomator(page, limits={}))


def try_send_invitation(
    page: Any, *, note_text: str, run_logs_dir: Path, profile_tag: str
) -> tuple[bool, str, str]:
    """Delegate to playwright connect flow with shared jitter pacing."""
    from linkedin_connect_flow import playwright_try_send_invitation

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
            automation, base_url=base_url, headed=headed
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


def _unpack_queue_item(item: tuple[str, ...]) -> tuple[str, str, str]:
    """(profile_url, variant_slug, search_intent)."""
    if len(item) >= 3:
        return item[0], item[1], item[2]
    return item[0], item[1], ""


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
) -> list[tuple[str, str, str]] | None:
    """Harvest People-search URLs (+ retry queue ordering). ``None`` = fatal blocker."""
    queries_map = search.get("queries_by_variant") or {}
    if not isinstance(queries_map, dict) or not queries_map:
        return []

    queued: list[tuple[str, str, str]] = []
    local_seen = set(seen_profiles)
    variants = list(queries_map.keys())

    if args.variant_filter:
        if args.variant_filter not in variants:
            print(
                f"Unknown variant slug {args.variant_filter!r}; known: {variants}",
                file=sys.stderr,
            )
            return []
        variants = [args.variant_filter]

    for slug in variants:
        merged = merged_queries_for_variant(raw_cfg, slug)
        if not merged:
            continue
        need = scoring_cap - len(queued)
        if need <= 0:
            break
        for qline, search_intent in merged:
            need_inner = scoring_cap - len(queued)
            if need_inner <= 0:
                break
            ql = str(qline or "").strip()
            if not ql:
                continue

            url = people_search_url(ql, base_url)

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

            new_urls = harvest_profile_urls(
                automation,
                max_new=max(need_inner * 10, 32),
                seed_seen=local_seen,
                cfg_limits=limits,
            )

            for u in new_urls:
                if len(queued) >= scoring_cap:
                    break
                queued.append((u, slug, search_intent))
                local_seen.add(u)

    retry_first = read_retry_connect_queue(RECRUITERS_CSV)
    pilot_mode = args.max_connections_override is not None

    if retry_first:
        retry_urls = {u for u, _ in retry_first}
        retry_triples = [(u, v, "") for u, v in retry_first]
        queued = retry_triples + [
            (u, v, i) for u, v, i in queued if u not in retry_urls
        ]
        print(
            f"Retrying {len(retry_first)} profile(s) with prior Connect failures first.",
            flush=True,
        )
    elif pilot_mode and not getattr(args, "dry_run", False):
        queued = queued[: min(len(queued), 8)]

    return queued


def run_recruiter_campaign(
    automation: LinkedInAutomatorBase,
    args: argparse.Namespace,
    raw_cfg: dict[str, Any],
    *,
    shutdown_browser: Callable[[], None],
    queued_override: list[tuple[str, str]] | None = None,
    skip_discovery: bool = False,
    action_plan_sink: Callable[[dict[str, Any]], None] | None = None,
    planned_invites: dict[str, dict[str, Any]] | None = None,
) -> int:
    ensure_recruiter_csv_schema(RECRUITERS_CSV)
    RUN_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    base_url = (raw_cfg.get("linkedin_base_url") or "https://www.linkedin.com").rstrip(
        "/"
    )
    limits = cfg_limits(raw_cfg)
    matcher = cfg_matching(raw_cfg)
    search = cfg_search(raw_cfg)

    if args.max_connections_override is not None:
        max_connect_daily = int(args.max_connections_override)
    else:
        max_connect_daily = effective_daily_invite_cap(limits)

    scoring_cap = int(limits.get("max_profiles_scored_per_run", 40))

    queries_map = search.get("queries_by_variant") or {}
    if not skip_discovery:
        if not isinstance(queries_map, dict) or not queries_map:
            print("search.queries_by_variant is missing or empty.", file=sys.stderr)
            return 2

    min_score = float(matcher.get("min_primary_score", 12))
    min_margin = float(matcher.get("min_margin_over_second", 4.0))
    require_clear = bool(matcher.get("require_clear_winner", False))
    require_gate = bool(matcher.get("require_recruiter_gate", True))

    note_templates_raw = raw_cfg.get("connection_notes") or {}
    if not isinstance(note_templates_raw, dict):
        note_templates_raw = {}

    seen_profiles = read_seen_profile_urls(RECRUITERS_CSV)
    skip_revisit = read_skip_revisit_urls(RECRUITERS_CSV)

    sent_logged_today = count_status_today(RECRUITERS_CSV, status="sent")
    invites_remaining_today = max(0, max_connect_daily - sent_logged_today)

    invites_sent_this_session = 0

    pilot_mode = args.max_connections_override is not None
    if pilot_mode:
        limits = {
            **limits,
            "delay_seconds_min": min(float(limits.get("delay_seconds_min", 45)), 12.0),
            "delay_seconds_max": min(float(limits.get("delay_seconds_max", 120)), 25.0),
        }

    print(
        f"Daily invite limits: cap={max_connect_daily} (logged_today={sent_logged_today} "
        f"remaining={invites_remaining_today}) scrape_cap={scoring_cap} dry_run={args.dry_run}",
        flush=True,
    )

    block = _warmup_and_maybe_login(
        automation,
        base_url=base_url,
        headed=args.headed,
        limits=limits,
        shutdown_browser=shutdown_browser,
    )
    if block:
        print(f"Halted warmup: {block}", flush=True)
        return 3

    if skip_discovery:
        queued = [_unpack_queue_item(t) for t in (queued_override or [])]
    else:
        qres = collect_discovery_queue_for_session(
            automation,
            raw_cfg=raw_cfg,
            args=args,
            scoring_cap=scoring_cap,
            limits=limits,
            search=search,
            base_url=base_url,
            shutdown_browser=shutdown_browser,
            seen_profiles=seen_profiles,
        )
        if qres is None:
            return 3
        queued = qres

    print(f"Queued profiles: {len(queued)} / cap {scoring_cap}", flush=True)

    today_iso = date.today().isoformat()
    idle_stride = random.randint(4, 5)

    for profile_idx, queue_item in enumerate(queued):
        canonical_url, search_variant_slug, search_intent = _unpack_queue_item(
            queue_item
        )
        if (
            not args.dry_run
            and invites_sent_this_session + sent_logged_today >= max_connect_daily
        ):
            print("Stopped: daily invitation budget exhausted.", flush=True)
            break

        if canonical_url in skip_revisit:
            continue

        if profile_idx > 0:
            if profile_idx % idle_stride == 0:
                idle_feed_automation(automation, base_url=base_url, limits=limits)
            else:
                between_profiles_delay(limits)

        if not automation_goto_or_closed(automation, canonical_url):
            shutdown_browser()
            return 4

        action_delay(limits)
        dwell_navigation(limits)

        block3 = assert_blocked_automation(automation)
        if block3:
            append_recruiter_row(
                recruiter_row_partial(
                    date_iso=today_iso,
                    profile_url=canonical_url,
                    variant_slug=search_variant_slug,
                    confidence=block3,
                    status="blocked",
                    skip_reason=block3,
                )
            )
            shutdown_browser()
            print(f"Halted visiting profile ({block3}).", flush=True)
            return 3

        scraped_payload = automation_evaluate_or_closed(
            automation, lis.PROFILE_SCRAPER_JS
        )
        if scraped_payload is None:
            shutdown_browser()
            return 4
        scraped_payload = scraped_payload or {}

        if lis.profile_page_load_failed(
            sample_automation_html(automation, cap=120_000)
        ):
            append_recruiter_row(
                recruiter_row_partial(
                    date_iso=today_iso,
                    profile_url=canonical_url,
                    name="",
                    headline="",
                    variant_slug=search_variant_slug,
                    status="skipped_profile_load_error",
                    skip_reason="linkedin_profile_page_load_error",
                )
            )
            print(
                f"Skipped (LinkedIn profile error): {canonical_url}",
                flush=True,
            )
            continue

        display_name = (scraped_payload.get("name") or "").strip()
        headline = (scraped_payload.get("headline") or "").strip()
        about = (scraped_payload.get("about") or "").strip()
        roles_txt = str(scraped_payload.get("role_text") or "").strip()
        location_txt = str(scraped_payload.get("location") or "").strip()
        company_guess_str = str(scraped_payload.get("companyGuess") or "").strip()

        headline_for_match = headline or display_name or "talent recruiter"

        if looks_pending_automation(automation):
            append_recruiter_row(
                recruiter_row_partial(
                    date_iso=today_iso,
                    profile_url=canonical_url,
                    name=display_name,
                    headline=headline,
                    variant_slug=search_variant_slug,
                    status="skipped_pending",
                    skip_reason="pending_visible",
                )
            )
            continue

        planned_invite = planned_invite_for_url(planned_invites, canonical_url)
        use_frozen_plan = bool(planned_invite.get("note")) and not bool(
            getattr(args, "revalidate", False)
        )

        if use_frozen_plan:
            frozen_variant = str(
                planned_invite.get("cv_variant")
                or planned_invite.get("variant_slug")
                or search_variant_slug
            )
            scoring_result = {
                "recommendation": {
                    "variant_slug": frozen_variant,
                    "primary_score": planned_invite.get("rank_score") or 0,
                    "margin_over_second": 4.0,
                    "confidence": "clear_winner",
                    "cv_primary_score": 12.0,
                },
                "recruiter_meta": {
                    "recruiter_gate_ok": True,
                    "sales_only_no_hiring": False,
                    "top_signals": "",
                    "sector_slug": frozen_variant,
                    "sector_top_score": 6.0,
                    "profile_blob_excerpt": "\n".join(
                        x
                        for x in (
                            headline_for_match,
                            company_guess_str,
                            about[:600],
                            roles_txt[:400],
                            location_txt,
                        )
                        if (x or "").strip()
                    )[:600],
                },
                "runner_up": {},
            }
        else:
            try:
                scoring_result = match_recruiter_profile(
                    headline=headline_for_match,
                    name=display_name,
                    profile_url=canonical_url,
                    company=company_guess_str,
                    about=about,
                    role_text=roles_txt,
                    location=location_txt,
                    recruiter_cfg=raw_cfg,
                )
            except ValueError:
                salvage = (
                    "\n\n".join(
                        chunk
                        for chunk in (about[:12000], roles_txt[:14000])
                        if (chunk or "").strip()
                    )
                    or "."
                )
                try:
                    scoring_result = match_recruiter_profile(
                        headline=headline_for_match,
                        name=display_name,
                        profile_url=canonical_url,
                        company=company_guess_str,
                        about=salvage,
                        role_text=roles_txt,
                        location=location_txt,
                        recruiter_cfg=raw_cfg,
                    )
                except Exception as exc_vf:
                    append_recruiter_row(
                        recruiter_row_partial(
                            date_iso=today_iso,
                            profile_url=canonical_url,
                            name=display_name,
                            headline=headline,
                            variant_slug=search_variant_slug,
                            status="error_match",
                            skip_reason=f"matching_failed:{exc_vf}",
                        )
                    )
                    continue

        recommendation = scoring_result.get("recommendation") or {}
        meta = scoring_result.get("recruiter_meta") or {}
        runner = scoring_result.get("runner_up") or {}

        if meta.get("recruiter_gate_ok"):
            blob_for_gate = "\n".join(
                x
                for x in (
                    headline_for_match,
                    about[:2000],
                    roles_txt[:1200],
                    company_guess_str,
                )
                if (x or "").strip()
            ).lower()
            gate_hits = matched_hiring_gate_terms(
                blob_for_gate, gate_terms_from_recruiter_cfg(raw_cfg)
            )
            leadership_hits = [t for t in gate_hits if t in _LEADERSHIP_GATE_LOG_TERMS]
            if leadership_hits:
                print(
                    f"Hiring gate OK — {display_name or canonical_url}: "
                    f"{', '.join(leadership_hits[:3])}",
                    flush=True,
                )

        best_variant = str(
            recommendation.get("variant_slug") or search_variant_slug or ""
        )

        primary_score_disp = recommendation.get("primary_score", "")
        confidence = str(recommendation.get("confidence") or "")
        margin_disp = recommendation.get("margin_over_second", "")
        runner_up_slug = str(
            recommendation.get("runner_up_slug") or runner.get("variant_slug") or ""
        )
        runner_up_score = str(
            recommendation.get("runner_up_score") or runner.get("primary_score") or ""
        )

        top_sig = str(meta.get("top_signals") or "")

        company_blob_lower = "\n".join(
            [headline_for_match, company_guess_str, about[:2000], roles_txt],
        ).lower()
        tier_slug, tier_refusal = assign_best_tier(
            result=scoring_result,
            cfg=raw_cfg,
            company_blob_lower=company_blob_lower,
        )

        okay, refusal = should_send_recruiter_connection(
            scoring_result,
            min_primary_score=min_score,
            min_margin_over_second=min_margin,
            require_clear_winner=require_clear,
            require_recruiter_gate=require_gate,
            full_cfg=raw_cfg,
        )
        if use_frozen_plan:
            okay = True
            refusal = ""

        nb = prepare_outreach_note_bundle(
            match_result=scoring_result,
            headline=headline,
            about=about,
            location_txt=location_txt,
            display_name=display_name,
            search_variant_slug=search_variant_slug,
            meta_signals_csv=top_sig,
            note_templates_raw=note_templates_raw,
            matching_cfg=matcher,
            profiles_path=None,
        )
        drafted_note_live = nb.get("note_live_full") or ""
        drafted_note_preview = nb.get("preview_with_fallback") or ""
        note_preview_trim = nb.get("note_preview_trim") or ""
        template_literal = nb.get("template_used") or ""
        if planned_invite.get("note"):
            drafted_note_live = str(planned_invite.get("note") or "")[:280]
            drafted_note_preview = drafted_note_live
            note_preview_trim = drafted_note_live[:220]
            template_literal = template_literal or "__planned_hiring_network_note__"

        if action_plan_sink is not None:
            action_plan_sink(
                {
                    "schema": "linkedin_recruit_scout_v1",
                    "date_iso": today_iso,
                    "profile_url": canonical_url,
                    "search_variant_slug": search_variant_slug,
                    "search_intent": search_intent,
                    "tier": tier_slug,
                    "tier_refusal": tier_refusal,
                    "name": display_name,
                    "headline": headline,
                    "company_guess": company_guess_str,
                    "scraped_about_excerpt": about[:420],
                    "variant_slug_best": best_variant,
                    "primary_score": recommendation.get("primary_score"),
                    "margin_over_second": recommendation.get("margin_over_second"),
                    "confidence": confidence,
                    "recruiter_gate_ok": meta.get("recruiter_gate_ok"),
                    "would_send_under_matching_rules": okay,
                    "matching_refusal": refusal,
                    "note_live_full": drafted_note_live,
                    "note_preview_trim": note_preview_trim,
                    "connection_template_slug": template_literal,
                },
            )

        prof_tag = profile_slug_from_url(canonical_url)

        row_base_common = recruiter_row_partial(
            date_iso=today_iso,
            profile_url=canonical_url,
            name=display_name,
            headline=headline,
            variant_slug=best_variant,
            primary_score=str(primary_score_disp),
            runner_up_slug=runner_up_slug,
            runner_up_score=runner_up_score,
            margin_over_second=str(margin_disp),
            top_signals=top_sig,
            connect_path="",
            confidence=confidence,
            persona=planned_invite.get("persona") or "",
            rank_score=planned_invite.get("rank_score") or "",
            profile_confidence=planned_invite.get("profile_confidence") or "",
            safety_decision=planned_invite.get("safety_decision") or "",
            note_reason=planned_invite.get("note_reason") or "",
            final_note=drafted_note_live,
        )

        if args.scout_jsonl_only:
            continue

        if args.dry_run:
            dry_skip_reason = refusal if not okay else ""
            dry_status = "dry_run_would_connect"
            preview_snip_exp = ""

            if not template_literal:
                dry_status = "dry_run_would_skip"
                bits: list[str] = []
                trimmed = dry_skip_reason.strip()
                if trimmed:
                    bits.append(trimmed)
                bits.append("missing_connection_note_template")
                dry_skip_reason = ";".join(bits)
            elif not okay:
                dry_status = "dry_run_would_skip"
            else:
                preview_snip_exp = (
                    nb.get("preview_excerpt_logged") or (drafted_note_preview[:220])
                )

            append_recruiter_row(
                {
                    **row_base_common,
                    "status": dry_status,
                    "skip_reason": dry_skip_reason,
                    "note_preview": preview_snip_exp,
                }
            )

            continue

        if not okay:
            seen_profiles.add(canonical_url)
            append_recruiter_row(
                {
                    **row_base_common,
                    "status": "skipped",
                    "skip_reason": refusal,
                    "note_preview": "",
                }
            )
            continue

        if not template_literal:
            append_recruiter_row(
                {
                    **row_base_common,
                    "status": "skipped",
                    "skip_reason": "missing_connection_note_template",
                    "note_preview": "",
                }
            )

            continue

        invitation_okay = False
        invitation_msg = ""
        connect_path = ""
        try:
            invite_result = automation_try_invite_or_closed(
                automation,
                note_text=drafted_note_live,
                run_logs_dir=RUN_LOGS_DIR,
                profile_tag=prof_tag,
                jitter_sleep=jitter_sleep,
            )
            if invite_result[0] is None:
                shutdown_browser()
                return 4
            invitation_okay, invitation_msg, connect_path = invite_result
        except Exception as exc_outer:
            invitation_okay = False
            invitation_msg = f"invite_exception:{exc_outer}"
            connect_path = ""

        row_out = {
            **row_base_common,
            "connect_path": connect_path,
        }

        if invitation_okay:
            invites_sent_this_session += 1
            seen_profiles.add(canonical_url)
            append_recruiter_row(
                {
                    **row_out,
                    "status": "sent",
                    "skip_reason": invitation_msg or "",
                    "note_preview": note_preview_trim,
                }
            )
            cool = float(limits.get("cool_down_after_sent_seconds", 0))
            if cool > 0:
                time.sleep(cool)
            if invites_sent_this_session + sent_logged_today >= max_connect_daily:
                print("Daily invitation sent — stopping run.", flush=True)
                break
        else:
            seen_profiles.add(canonical_url)
            append_recruiter_row(
                {
                    **row_out,
                    "status": "skipped_no_connect",
                    "skip_reason": invitation_msg or "invite_failed_unknown",
                    "note_preview": (
                        drafted_note_live[:90] if drafted_note_live else ""
                    ),
                }
            )

    print("LinkedIn recruiter run finished.", flush=True)
    shutdown_browser()
    return 0


def run_linked_in_campaign_backend(
    args: argparse.Namespace,
    raw_cfg: dict[str, Any],
    *,
    queued_override: list[tuple[str, str]] | list[tuple[str, str, str]] | None = None,
    skip_discovery: bool = False,
    action_plan_sink: Callable[[dict[str, Any]], None] | None = None,
    planned_invites: dict[str, dict[str, Any]] | None = None,
) -> int:
    backend = backend_from_cfg(raw_cfg)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    RUN_LOGS_DIR.mkdir(parents=True, exist_ok=True)

    browsing = backend in {"browse_ws", "browse", "browse_cli"}

    if browsing:
        bb = cfg_browser(raw_cfg)
        port = bb.get("browse_debug_port", 9247)
        print(
            f"Browser: browse_ws (Chrome + browse CLI debugger port {port})  "
            f"profile_dir={PROFILE_DIR}",
            flush=True,
        )
        drv, daemon = start_browse_ws_session(raw_cfg)

        def shutdown_browser() -> None:
            pass

        try:
            return run_recruiter_campaign(
                drv,
                args,
                raw_cfg,
                shutdown_browser=shutdown_browser,
                queued_override=queued_override,
                skip_discovery=skip_discovery,
                action_plan_sink=action_plan_sink,
                planned_invites=planned_invites,
            )
        finally:
            daemon.stop()

    browser_channel = resolve_browser_channel(raw_cfg, args.browser_channel)
    browser_label = browser_channel or "chromium (Playwright bundle)"
    print(f"Browser: {browser_label}  profile_dir={PROFILE_DIR}", flush=True)

    with sync_playwright() as playwright:
        ctx = launch_linkedin_browser_context(
            playwright,
            headed=args.headed,
            channel=browser_channel,
        )

        page_l = ctx.pages[0] if ctx.pages else ctx.new_page()
        automation = PlaywrightLinkedInAutomator(page_l, cfg_limits(raw_cfg))

        closed_ctx = {"done": False}

        def shutdown_browser() -> None:
            if closed_ctx["done"]:
                return
            closed_ctx["done"] = True
            try:
                ctx.close()
            except Exception:
                pass

        try:
            return run_recruiter_campaign(
                automation,
                args,
                raw_cfg,
                shutdown_browser=shutdown_browser,
                queued_override=queued_override,
                skip_discovery=skip_discovery,
                action_plan_sink=action_plan_sink,
                planned_invites=planned_invites,
            )

        finally:
            shutdown_browser()


def run_bot(args: argparse.Namespace, raw_cfg: dict[str, Any]) -> int:
    return run_linked_in_campaign_backend(args, raw_cfg)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="CV-matched LinkedIn recruiter automation")

    ap.add_argument(
        "--headed",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Show browser (--no-headed enables headless mode).",
    )

    ap.add_argument(
        "--dry-run", action="store_true", help="Score only; never send invites."
    )
    ap.add_argument(
        "--revalidate",
        action="store_true",
        help="Re-score profiles even when a planned note exists in the dispatch queue.",
    )
    ap.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"YAML config (default {DEFAULT_CONFIG})",
    )

    ap.add_argument(
        "--max",
        dest="max_connections_override",
        type=int,
        default=None,
        help="Override max_connections_per_day for today",
    )

    ap.add_argument(
        "--variant",
        dest="variant_filter",
        default=None,
        help="Restrict discovery to one CV slug declared in queries_by_variant (e.g., luxury-retail)",
    )

    ap.add_argument(
        "--scout-jsonl-only",
        action="store_true",
        help="Append recruiter_action_plan.jsonl only (orchestrator scout); skips recruiters.csv updates.",
    )

    ap.add_argument(
        "--browser-channel",
        dest="browser_channel",
        default=None,
        help=(
            "Override config browser.channel: chrome (installed Google Chrome), "
            "chromium (Playwright bundle), chrome-beta, msedge, …"
        ),
    )

    return ap


def main(argv: list[str] | None = None) -> int:

    parsed = build_arg_parser().parse_args(argv)

    raw = load_config(Path(parsed.config))

    return run_bot(parsed, raw)


if __name__ == "__main__":
    sys.exit(main())
