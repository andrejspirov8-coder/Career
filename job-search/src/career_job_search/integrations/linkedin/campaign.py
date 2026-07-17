#!/usr/bin/env python3
"""
LinkedIn recruiter scout: People search → profile scrape → CV match → optional connection invite.

Run from `job-search/`:
  python3 tools/linkedin_recruiter_bot.py --headed --dry-run
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import date as date
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from career_job_search.integrations.linkedin.browser import (
    PlaywrightLinkedInAutomator,
    backend_from_cfg,
    start_browse_ws_session,
)
from career_job_search.integrations.linkedin.campaign_config import (
    DEFAULT_CONFIG as DEFAULT_CONFIG,
)
from career_job_search.integrations.linkedin.campaign_config import (
    SUPPORTED_BROWSER_CHANNELS as SUPPORTED_BROWSER_CHANNELS,
)
from career_job_search.integrations.linkedin.campaign_config import (
    _profile_in_use_exit_message as _profile_in_use_exit_message,
)
from career_job_search.integrations.linkedin.campaign_config import (
    accept_rate_from_csv as accept_rate_from_csv,
)
from career_job_search.integrations.linkedin.campaign_config import (
    action_delay as action_delay,
)
from career_job_search.integrations.linkedin.campaign_config import (
    between_profiles_delay as between_profiles_delay,
)
from career_job_search.integrations.linkedin.campaign_config import (
    cfg_browser as cfg_browser,
)
from career_job_search.integrations.linkedin.campaign_config import (
    cfg_limits as cfg_limits,
)
from career_job_search.integrations.linkedin.campaign_config import (
    cfg_matching as cfg_matching,
)
from career_job_search.integrations.linkedin.campaign_config import (
    cfg_recruiter_matching as cfg_recruiter_matching,
)
from career_job_search.integrations.linkedin.campaign_config import (
    cfg_search as cfg_search,
)
from career_job_search.integrations.linkedin.campaign_config import (
    count_status_today as count_status_today,
)
from career_job_search.integrations.linkedin.campaign_config import (
    dwell_navigation as dwell_navigation,
)
from career_job_search.integrations.linkedin.campaign_config import (
    effective_daily_invite_cap as effective_daily_invite_cap,
)
from career_job_search.integrations.linkedin.campaign_config import (
    idle_feed_browse as idle_feed_browse,
)
from career_job_search.integrations.linkedin.campaign_config import (
    jitter_sleep as jitter_sleep,
)
from career_job_search.integrations.linkedin.campaign_config import (
    launch_linkedin_browser_context as launch_linkedin_browser_context,
)
from career_job_search.integrations.linkedin.campaign_config import (
    load_config as load_config,
)
from career_job_search.integrations.linkedin.campaign_config import (
    people_search_url as people_search_url,
)
from career_job_search.integrations.linkedin.campaign_config import (
    planned_invite_for_url as planned_invite_for_url,
)
from career_job_search.integrations.linkedin.campaign_config import (
    profile_slug_from_url as profile_slug_from_url,
)
from career_job_search.integrations.linkedin.campaign_config import (
    read_retry_connect_queue as read_retry_connect_queue,
)
from career_job_search.integrations.linkedin.campaign_config import (
    read_seen_profile_urls as read_seen_profile_urls,
)
from career_job_search.integrations.linkedin.campaign_config import (
    read_skip_revisit_urls as read_skip_revisit_urls,
)
from career_job_search.integrations.linkedin.campaign_config import (
    resolve_browser_channel as resolve_browser_channel,
)
from career_job_search.integrations.linkedin.campaign_config import (
    successful_sends_today as successful_sends_today,
)
from career_job_search.integrations.linkedin.campaign_runner import (
    run_recruiter_campaign as run_recruiter_campaign,
)
from career_job_search.integrations.linkedin.campaign_session import (
    _unpack_queue_item as _unpack_queue_item,
)
from career_job_search.integrations.linkedin.campaign_session import (
    _warmup_and_maybe_login as _warmup_and_maybe_login,
)
from career_job_search.integrations.linkedin.campaign_session import (
    assert_blocked_automation as assert_blocked_automation,
)
from career_job_search.integrations.linkedin.campaign_session import (
    assert_not_blocked as assert_not_blocked,
)
from career_job_search.integrations.linkedin.campaign_session import (
    automation_evaluate_or_closed as automation_evaluate_or_closed,
)
from career_job_search.integrations.linkedin.campaign_session import (
    automation_goto_or_closed as automation_goto_or_closed,
)
from career_job_search.integrations.linkedin.campaign_session import (
    automation_try_invite_or_closed as automation_try_invite_or_closed,
)
from career_job_search.integrations.linkedin.campaign_session import (
    browser_was_closed as browser_was_closed,
)
from career_job_search.integrations.linkedin.campaign_session import (
    collect_discovery_queue_for_session as collect_discovery_queue_for_session,
)
from career_job_search.integrations.linkedin.campaign_session import (
    harvest_profile_urls as harvest_profile_urls,
)
from career_job_search.integrations.linkedin.campaign_session import (
    idle_feed_automation as idle_feed_automation,
)
from career_job_search.integrations.linkedin.campaign_session import (
    looks_pending_automation as looks_pending_automation,
)
from career_job_search.integrations.linkedin.campaign_session import (
    looks_pending_connection as looks_pending_connection,
)
from career_job_search.integrations.linkedin.campaign_session import (
    sample_automation_html as sample_automation_html,
)
from career_job_search.integrations.linkedin.campaign_session import (
    sample_html as sample_html,
)
from career_job_search.integrations.linkedin.campaign_session import (
    try_send_invitation as try_send_invitation,
)
from career_job_search.integrations.linkedin.campaign_session import (
    wait_for_manual_login as wait_for_manual_login,
)
from career_job_search.integrations.linkedin.campaign_session import (
    wait_for_manual_login_automation as wait_for_manual_login_automation,
)
from career_job_search.integrations.linkedin.paths import PROFILE_DIR, RUN_LOGS_DIR
from career_job_search.recruiters.policy import (
    current_send_mode,
    validate_live_dispatch_max,
)
from career_job_search.recruiters.policy import (
    live_dispatch_slots_remaining as live_dispatch_slots_remaining,
)


def run_linked_in_campaign_backend(
    args: argparse.Namespace,
    raw_cfg: dict[str, Any],
    *,
    queued_override: list[tuple[str, str]] | list[tuple[str, str, str]] | None = None,
    skip_discovery: bool = False,
    action_plan_sink: Callable[[dict[str, Any]], None] | None = None,
    planned_invites: dict[str, dict[str, Any]] | None = None,
) -> int:
    live_dispatch = not getattr(args, "dry_run", False) and not getattr(
        args, "scout_jsonl_only", False
    )
    validated_max = validate_live_dispatch_max(
        getattr(args, "max_connections_override", None),
        dry_run=not live_dispatch,
        option_name="--max",
    )
    if validated_max is not None:
        args.max_connections_override = validated_max
    if live_dispatch and current_send_mode() == "manual":
        raise SystemExit(
            "Manual LinkedIn send mode is active. Use the dashboard or CLI "
            "dry-run output to open profiles, copy approved notes, and record "
            "manual outcomes."
        )
    if live_dispatch and not getattr(args, "allow_live_dispatch", False):
        raise SystemExit(
            "Live LinkedIn dispatch is blocked by default. Use --dry-run first, "
            "then add --allow-live-dispatch only after manual queue review."
        )

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
        "--allow-live-dispatch",
        action="store_true",
        help="Required for non-dry-run LinkedIn connection dispatch after manual review.",
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
