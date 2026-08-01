"""Bounded LinkedIn recruiter campaign execution loop."""

from __future__ import annotations

import argparse
import random
import sys
import time
from collections.abc import Callable
from datetime import date
from typing import Any

from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.browser import LinkedInAutomatorBase
from career_job_search.integrations.linkedin.campaign_config import (
    action_delay,
    between_profiles_delay,
    cfg_limits,
    cfg_matching,
    cfg_search,
    dwell_navigation,
    effective_daily_invite_cap,
    jitter_sleep,
    planned_invite_for_url,
    profile_slug_from_url,
    read_seen_profile_urls,
    read_skip_revisit_urls,
    successful_sends_today,
)
from career_job_search.integrations.linkedin.campaign_session import (
    _LEADERSHIP_GATE_LOG_TERMS,
    _unpack_queue_item,
    _warmup_and_maybe_login,
    assert_blocked_automation,
    automation_evaluate_or_closed,
    automation_goto_or_closed,
    automation_try_invite_or_closed,
    collect_discovery_queue_for_session,
    idle_feed_automation,
    looks_pending_automation,
    sample_automation_html,
)
from career_job_search.integrations.linkedin.paths import (
    PROFILE_DIR,
    RECRUITERS_CSV,
    RUN_LOGS_DIR,
)
from career_job_search.recruiters.log import (
    append_recruiter_row,
    ensure_recruiter_csv_schema,
    recruiter_row_partial,
)
from career_job_search.recruiters.matching import (
    assign_best_tier,
    gate_terms_from_recruiter_cfg,
    match_recruiter_profile,
    matched_hiring_gate_terms,
    prepare_outreach_note_bundle,
    profile_has_outreach_exclude,
    should_send_recruiter_connection,
)
from career_job_search.recruiters.policy import (
    MAX_LIVE_DISPATCH,
    live_dispatch_slots_remaining,
)
from career_job_search.recruiters.repository import live_dispatch_ledger_lock, mark_sent


def verified_target_company_outreach_allowed(
    result: dict[str, Any],
    *,
    target_company_verified: bool,
    current_search_evidence: str,
    full_cfg: dict[str, Any],
) -> bool:
    """Allow outreach to a verified hiring-company contact despite low generic CV fit.

    Keeps current-role exclusions intact: a verified company match does not
    override outreach_exclude_terms (e.g. staffing agencies).
    """
    if not target_company_verified:
        return False
    meta = result.get("recruiter_meta") or {}
    if not meta.get("recruiter_gate_ok") or meta.get("sales_only_no_hiring"):
        return False
    blob = (current_search_evidence or "").lower()
    if profile_has_outreach_exclude(blob, full_cfg):
        return False
    return True


def target_aware_variant_slug(
    recommendation: dict[str, Any],
    *,
    search_variant_slug: str,
    verified_target_allowed: bool,
) -> str:
    """Pick the CV variant for outreach: the job's variant when a verified target
    company is allowed, otherwise the profile-matched recommendation variant."""
    if verified_target_allowed:
        return search_variant_slug or ""
    return str(recommendation.get("variant_slug") or search_variant_slug or "")


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
        max_connect_daily = min(
            MAX_LIVE_DISPATCH,
            int(args.max_connections_override),
        )
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

    sent_logged_today = successful_sends_today()
    invites_remaining_today = live_dispatch_slots_remaining(
        sent_logged_today,
        requested_max=max_connect_daily,
    )

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
    idle_stride = random.randint(4, 5)  # noqa: S311

    for profile_idx, queue_item in enumerate(queued):
        canonical_url, search_variant_slug, search_intent = _unpack_queue_item(
            queue_item
        )
        if not args.dry_run and successful_sends_today() >= max_connect_daily:
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

        # Apply dispatch safety checks for token leakage (curly brackets)
        from career_job_search.recruiters.dispatch_guard import validate_note_integrity

        note_safe, note_reason = validate_note_integrity(drafted_note_live)
        if not note_safe:
            print(
                f"⚠️ SAFETY REFUSAL: Gated dispatch for {canonical_url} - {note_reason}",
                flush=True,
            )
            append_recruiter_row(
                recruiter_row_partial(
                    date_iso=today_iso,
                    profile_url=canonical_url,
                    name=display_name,
                    headline=headline,
                    variant_slug=search_variant_slug,
                    status="skipped_failed_safety",
                    skip_reason=note_reason,
                    final_note=drafted_note_live,
                )
            )
            continue

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

        daily_budget_exhausted = False
        invitation_okay = False
        invitation_msg = ""
        connect_path = ""
        with live_dispatch_ledger_lock():
            # Re-read both ledgers while holding the cross-process lock. This is
            # the final check immediately before a browser click can send.
            if successful_sends_today() >= max_connect_daily:
                daily_budget_exhausted = True
            else:
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

                seen_profiles.add(canonical_url)
                if invitation_okay:
                    mark_sent(
                        profile_url=canonical_url,
                        note=drafted_note_live,
                        run_id=f"linkedin-bot-{today_iso}",
                        reason=invitation_msg or "linkedin_invite_sent",
                        metadata={
                            "name": display_name,
                            "headline": headline,
                            "variant_slug": best_variant,
                            "connect_path": connect_path,
                        },
                    )
                    append_recruiter_row(
                        {
                            **row_out,
                            "status": "sent",
                            "skip_reason": invitation_msg or "",
                            "note_preview": note_preview_trim,
                        }
                    )
                else:
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

        if daily_budget_exhausted:
            print("Stopped: daily invitation budget exhausted.", flush=True)
            break
        if invitation_okay:
            cool = float(limits.get("cool_down_after_sent_seconds", 0))
            if cool > 0:
                time.sleep(cool)
            if successful_sends_today() >= max_connect_daily:
                print("Daily invitation sent — stopping run.", flush=True)
                break

    print("LinkedIn recruiter run finished.", flush=True)
    shutdown_browser()
    return 0
