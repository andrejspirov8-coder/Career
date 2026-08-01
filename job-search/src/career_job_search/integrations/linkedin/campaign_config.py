"""Configuration, pacing, and durable-ledger helpers for LinkedIn campaigns."""

from __future__ import annotations

import csv
import math
import random
import re
import time
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

from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.paths import (
    DEFAULT_LINKEDIN_CONFIG,
    PROFILE_DIR,
    RECRUITERS_CSV,
)
from career_job_search.integrations.linkedin.profile_lock import (
    describe_profile_lock,
    is_profile_in_use_error,
    release_stale_chrome_profile_lock,
)
from career_job_search.recruiters.policy import MAX_LIVE_DISPATCH
from career_job_search.recruiters.repository import (
    DEFAULT_STATE_DB,
    sent_profile_urls_on_local_date,
)

DEFAULT_CONFIG = DEFAULT_LINKEDIN_CONFIG

# Version of the checked-in linkedin/config.yaml structure. Unknown future
# versions are rejected at load time so schema drift fails loudly instead of
# being silently ignored. See docs/SCHEMAS.md.
CAMPAIGN_CONFIG_SCHEMA_VERSION = "campaign_config_v1"

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
    version = cfg.get("schema_version")
    if version is not None and version != CAMPAIGN_CONFIG_SCHEMA_VERSION:
        raise SystemExit(
            f"Unsupported linkedin/config.yaml schema_version {version!r} "
            f"(expected {CAMPAIGN_CONFIG_SCHEMA_VERSION!r}). "
            "See docs/SCHEMAS.md for the current schema."
        )
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

    The configured caps are always clamped to the three-send live ceiling.
    """
    full_cap = int(limits.get("max_connections_per_day", MAX_LIVE_DISPATCH))
    low_cap = int(limits.get("max_connections_per_day_low_accept", MAX_LIVE_DISPATCH))
    need_rate = float(limits.get("min_accept_rate_for_full_cap", 0.4))
    min_sent = int(limits.get("min_sent_for_accept_rate", 5))
    rate = accept_rate_from_csv(csv_path)
    if rate is None:
        selected_cap = low_cap
        return min(MAX_LIVE_DISPATCH, max(0, selected_cap))
    with csv_path.open(encoding="utf-8", newline="") as f:
        n_sent = sum(
            1
            for row in csv.DictReader(f)
            if (row.get("status") or "").strip() == "sent"
        )
    if n_sent < min_sent:
        selected_cap = low_cap
    elif rate < need_rate:
        selected_cap = min(full_cap, low_cap)
    else:
        selected_cap = full_cap
    return min(MAX_LIVE_DISPATCH, max(0, selected_cap))


def profile_slug_from_url(url: str) -> str:
    m = re.search(r"\/in\/([^\/?#]+)", (url or "").split("?")[0], re.I)
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
        page.mouse.wheel(0, random.randint(320, 1100))  # noqa: S311
    except Exception:  # noqa: S110
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
        "- Run: python3 -m career_job_search.recruiters.orchestrator preflight  (clears stale locks)\n"
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
    time.sleep(random.uniform(lo, hi))  # noqa: S311


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


def successful_sends_today(
    csv_path: Path = RECRUITERS_CSV,
    *,
    state_db: Path = DEFAULT_STATE_DB,
) -> int:
    """Read both durable ledgers so a new run sees every successful send."""

    today = date.today().isoformat()
    csv_urls: set[str] = set()
    csv_count = 0
    if csv_path.exists():
        with csv_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if (row.get("date_iso") or "") != today or (
                    row.get("status") or ""
                ) != "sent":
                    continue
                csv_count += 1
                canonical = lis.canonical_profile_url(row.get("profile_url") or "")
                if canonical:
                    csv_urls.add(canonical)
    sqlite_urls = sent_profile_urls_on_local_date(db_path=state_db)
    return max(csv_count, len(csv_urls | sqlite_urls))


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
