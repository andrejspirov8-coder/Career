#!/usr/bin/env python3
"""LinkedIn recruiter orchestrator — scout JSONL → session plan → dispatch.

Run from ``job-search/``::

  python3 tools/recruiter_orchestrate.py preflight
  python3 tools/recruiter_orchestrate.py scout --headed
  python3 tools/recruiter_orchestrate.py plan --tier tier_1
  python3 tools/recruiter_orchestrate.py dispatch --headed --tier tier_1 --dry-run
  python3 tools/recruiter_orchestrate.py daily --headed --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

from career_job_search.cvs.matching import CV_DIR, PROFILES_PATH, load_profiles
from career_job_search.integrations.linkedin import campaign as bot
from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.browser import browse_debug_port
from career_job_search.integrations.linkedin.paths import (
    ACTION_PLAN_JSONL,
    JOB_ROOT,
    PROFILE_DIR,
    RECRUITERS_CSV,
    SESSION_STATE_JSON,
)
from career_job_search.integrations.linkedin.profile_lock import (
    describe_profile_lock,
    release_stale_chrome_profile_lock,
)
from career_job_search.recruiters.policy import (
    can_attempt_live_dispatch,
    current_send_mode,
    validate_live_dispatch_max,
)
from career_job_search.recruiters.repository import DEFAULT_STATE_DB, require_approvals
from career_job_search.recruiters.run_state import (
    initial_snapshot,
    save_run_state,
    save_snapshot,
)
from career_job_search.recruiters.workflow import initialise_run_state
from career_job_search.recruiters.workflow_models import WorkflowStage

TOOLS_DIR = JOB_ROOT / "tools"


def _needs_yaml() -> None:
    if yaml is None:
        raise SystemExit("Install PyYAML: pip install pyyaml")


def load_yaml_config(path: Path) -> dict[str, Any]:
    _needs_yaml()
    if not path.exists():
        raise SystemExit(f"Missing config: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise SystemExit("Config root must be a YAML mapping.")
    return data


def campaign_config_with_overrides(
    cfg: dict[str, Any],
    *,
    max_profiles_scored: int | None = None,
    login_timeout_seconds: int | None = None,
    fast_dry_run: bool = False,
) -> dict[str, Any]:
    """Return a campaign config copy with local run-safety overrides."""
    out = dict(cfg)
    limits = dict(out.get("limits") or {})

    if max_profiles_scored is not None:
        limits["max_profiles_scored_per_run"] = max(1, int(max_profiles_scored))

    if login_timeout_seconds is not None:
        limits["login_timeout_seconds"] = max(0, int(login_timeout_seconds))

    if fast_dry_run:
        limits["dwell_after_navigate_seconds_min"] = min(
            float(limits.get("dwell_after_navigate_seconds_min", 2)), 1.0
        )
        limits["dwell_after_navigate_seconds_max"] = min(
            float(limits.get("dwell_after_navigate_seconds_max", 6)), 2.0
        )
        limits["action_delay_seconds_min"] = min(
            float(limits.get("action_delay_seconds_min", 1.5)), 0.5
        )
        limits["action_delay_seconds_max"] = min(
            float(limits.get("action_delay_seconds_max", 4.0)), 1.0
        )
        limits["between_profiles_seconds_median"] = min(
            float(limits.get("between_profiles_seconds_median", 70)), 3.0
        )
        limits["between_profiles_seconds_floor"] = min(
            float(limits.get("between_profiles_seconds_floor", 8)), 1.0
        )
        limits["between_profiles_seconds_cap"] = min(
            float(limits.get("between_profiles_seconds_cap", 420)), 5.0
        )
        limits["idle_browse_seconds_min"] = min(
            float(limits.get("idle_browse_seconds_min", 60)), 3.0
        )
        limits["idle_browse_seconds_max"] = min(
            float(limits.get("idle_browse_seconds_max", 120)), 6.0
        )

    out["limits"] = limits
    return out


def default_daily_scout_cap(
    *,
    dry_run: bool,
    max_dispatch: int | None,
    max_scout: int | None,
) -> int | None:
    if max_scout is not None:
        return max(1, int(max_scout))
    if not dry_run:
        return None
    if max_dispatch is not None:
        return max(1, int(max_dispatch))
    return 5


def chrome_debugger_reachable(cfg: dict[str, Any]) -> tuple[bool, str]:
    port = browse_debug_port(cfg)
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        with urlopen(url, timeout=2.5) as r:
            blob = json.loads(r.read())
        ws = blob.get("webSocketDebuggerUrl")
        if ws:
            return True, f"debugger_ok port={port}"
        return False, f"missing_ws_url port={port}"
    except (URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        return False, f"no_debugger_on_{port}:{exc!r}"


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl_latest_by_url(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    latest: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = (obj.get("profile_url") or "").strip()
            if not url:
                continue
            canon = lis.canonical_profile_url(url) or url.strip()
            latest[canon] = obj
    return latest


def merge_mcp_stubs_into_action_plan(
    mcp_path: Path,
    *,
    sink_path: Path = ACTION_PLAN_JSONL,
) -> int:
    """Append MCP harvest stubs as scout-shaped JSONL rows for hiring_network rank."""
    if not mcp_path.is_file():
        raise SystemExit(f"MCP harvest file not found: {mcp_path}")
    n = 0
    sink = scout_sink_factory(sink_path)
    with mcp_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                stub = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = (stub.get("profile_url") or "").strip()
            canon = lis.canonical_profile_url(url) or url
            if not canon or "/in/" not in canon:
                continue
            sink(
                {
                    "schema": "linkedin_recruit_scout_v1",
                    "source": "mcp_discovery",
                    "profile_url": canon,
                    "name": stub.get("name") or "",
                    "headline": stub.get("headline") or "",
                    "company_guess": stub.get("company") or "",
                    "location": stub.get("location") or "",
                    "about": stub.get("about") or "",
                    "role_text": stub.get("role_text") or "",
                    "search_variant_slug": stub.get("variant_slug") or "luxury-retail",
                    "search_intent": stub.get("search_intent") or "",
                }
            )
            n += 1
    print(f"Merged {n} MCP stub(s) into {sink_path}", flush=True)
    return n


def planned_invites_from_session(session: dict[str, Any]) -> dict[str, dict[str, Any]]:
    planned: dict[str, dict[str, Any]] = {}
    for row in session.get("queue") or []:
        if not isinstance(row, dict):
            continue
        canon = lis.canonical_profile_url(row.get("profile_url") or "")
        if not canon:
            continue
        planned[canon] = {
            "note": row.get("note_live_full") or "",
            "cv_variant": row.get("variant_slug_best")
            or row.get("search_variant_slug")
            or "",
            "variant_slug": row.get("variant_slug_best") or "",
            "persona": row.get("persona") or "",
            "rank_score": row.get("rank_score") or row.get("primary_score") or "",
            "profile_confidence": row.get("profile_confidence") or "",
            "safety_decision": row.get("safety_decision") or "approved",
            "note_reason": row.get("note_reason") or "",
        }
    return planned


def scout_sink_factory(path: Path) -> Callable[[dict[str, Any]], None]:
    def _sink(record: dict[str, Any]) -> None:
        append_jsonl(path, record)

    return _sink


def cmd_preflight(config_path: Path, *, browse_status: bool) -> int:
    cfg = load_yaml_config(config_path)

    variants = load_profiles(PROFILES_PATH)
    print(f"Profiles: {PROFILES_PATH} ({len(variants)} variant(s))")

    missing_md: list[str] = []
    for slug, block in variants.items():
        md_rel = block.get("markdown")
        if not isinstance(md_rel, str):
            continue
        p = CV_DIR / md_rel
        if not p.is_file():
            missing_md.append(f"{slug}: missing {p}")

    if missing_md:
        print("WARN – CV markdown gaps:", flush=True)
        for line in missing_md:
            print(f"  {line}", flush=True)

    limits = cfg.get("limits") or {}
    pacemaker = bot.effective_daily_invite_cap(limits)

    sent_today = bot.count_status_today(RECRUITERS_CSV, status="sent")
    print(f"Today's sent count (logged): {sent_today}")
    print(f"Effective invitation cap today: {pacemaker}")
    print(f"Automation profile dir: {PROFILE_DIR}")
    lock_before = describe_profile_lock(PROFILE_DIR)
    print(f"Profile lock: {lock_before}")
    if release_stale_chrome_profile_lock(PROFILE_DIR):
        print(
            f"Profile lock: cleared stale lock (now {describe_profile_lock(PROFILE_DIR)})"
        )
    cookies = PROFILE_DIR / "Default" / "Cookies"
    if cookies.is_file():
        print(f"Saved session cookies: yes ({cookies.stat().st_size // 1024} KB)")
    else:
        print(
            "Saved session cookies: not yet — run once with --headed and sign in "
            "in the automation Chrome window"
        )
    print(f"Action plan sink: {ACTION_PLAN_JSONL}")
    print(f"Session queue file: {SESSION_STATE_JSON}")

    if browse_status:
        ok, msg = chrome_debugger_reachable(cfg)
        tag = "OK" if ok else "offline"
        print(f"browse/chrome debugger: {tag} ({msg})", flush=True)
    return 0


def cmd_scout(
    *,
    config_path: Path,
    headed: bool,
    browser_channel: str | None,
    variant: str | None,
    sink_path: Path,
    max_profiles_scored: int | None = None,
    login_timeout_seconds: int | None = None,
    dry_run_context: bool = False,
) -> int:
    cfg = campaign_config_with_overrides(
        load_yaml_config(config_path),
        max_profiles_scored=max_profiles_scored,
        login_timeout_seconds=login_timeout_seconds,
        fast_dry_run=dry_run_context,
    )
    scout_args = argparse.Namespace(
        headed=headed,
        dry_run=dry_run_context,
        scout_jsonl_only=True,
        config=config_path,
        max_connections_override=None,
        variant_filter=variant,
        browser_channel=browser_channel,
    )

    return bot.run_linked_in_campaign_backend(
        scout_args,
        cfg,
        action_plan_sink=scout_sink_factory(sink_path),
    )


def build_session_queue_payload(
    cfg: dict[str, Any],
    *,
    tier_filter: str | None,
    retries_first: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    latest = read_jsonl_latest_by_url(ACTION_PLAN_JSONL)

    retries = bot.read_retry_connect_queue(RECRUITERS_CSV)
    retry_set = {lis.canonical_profile_url(u) or u for u, _ in retries}

    skip_urls = bot.read_skip_revisit_urls(RECRUITERS_CSV)

    ordered_keys: list[str] = []

    def push_key(canon_url: str) -> None:
        if canon_url in latest and canon_url not in ordered_keys:
            ordered_keys.append(canon_url)

    if retries_first:
        for ru, _ in retries:
            c = lis.canonical_profile_url(ru) or ru.strip()
            push_key(c)

        for canon in sorted(latest.keys()):
            if canon not in retry_set:
                push_key(canon)
    else:
        ordered_keys.extend(sorted(latest.keys()))

    out_rows: list[dict[str, Any]] = []

    tiers_cfg = cfg.get("tiers") or {}
    valid_tiers = {k for k in tiers_cfg if isinstance(k, str)}

    skipped = {"wrong_tier": 0, "skip_revisit": 0}

    tier_token = tier_filter.strip() if tier_filter else ""
    wants_tier = tier_token.lower() not in {"", "all"}

    def tier_ok(blob: dict[str, Any]) -> bool:
        if not wants_tier:
            return True
        rec_tier = (blob.get("tier") or "").strip()
        if tier_token not in valid_tiers:
            raise SystemExit(
                f"Unknown tier filter {tier_token!r}. Config has: {sorted(valid_tiers) or '(none)'}"
            )
        return rec_tier == tier_token

    for canon in ordered_keys:
        if canon in skip_urls:
            skipped["skip_revisit"] += 1
            continue

        blob = latest[canon]

        if not tier_ok(blob):
            skipped["wrong_tier"] += 1
            continue

        gate_ok = bool(blob.get("recruiter_gate_ok"))
        sends_ok = bool(blob.get("would_send_under_matching_rules"))
        sends_ok_eff = sends_ok if gate_ok else False

        if not sends_ok_eff:
            continue

        pv = blob.get("note_live_full") or ""
        preview = pv[:280].strip()

        out_rows.append(
            {
                "profile_url": canon,
                "search_variant_slug": (
                    (blob.get("search_variant_slug") or "").strip()
                    or (blob.get("variant_slug_best") or "").strip()
                ),
                "variant_slug_best": (blob.get("variant_slug_best") or "").strip(),
                "tier": (blob.get("tier") or "").strip(),
                "primary_score": blob.get("primary_score"),
                "note_live_full": pv,
                "note_preview_trim": preview,
                "name": blob.get("name") or "",
                "headline": blob.get("headline") or "",
            }
        )

    return out_rows, skipped


def cmd_plan(
    cfg_path: Path,
    *,
    tier_filter: str | None,
    retries_first: bool,
    mcp_source: Path | None = None,
) -> int:
    if mcp_source is not None:
        merge_mcp_stubs_into_action_plan(mcp_source)
    cfg = load_yaml_config(cfg_path)
    payload, skips = build_session_queue_payload(
        cfg, tier_filter=tier_filter, retries_first=retries_first
    )

    doc = {
        "schema": "recruiter_session_state_v1",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "config_path": str(cfg_path.resolve()),
        "tier_filter": tier_filter,
        "queue": payload,
        "skip_stats": skips,
        "blocked_reason": "",
    }
    run = initialise_run_state("session-plan")
    snapshot = initial_snapshot(run, WorkflowStage.DISCOVER)
    save_run_state(run)
    save_snapshot(snapshot)
    SESSION_STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    SESSION_STATE_JSON.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(
        f"Wrote {SESSION_STATE_JSON} with {len(payload)} dispatchable entr(y/ies); "
        f"skip_revisit_skips={skips['skip_revisit']} wrong_tier={skips['wrong_tier']}",
        flush=True,
    )

    preview_n = min(5, len(payload))
    if preview_n:
        print("Preview:")
        for row in payload[:preview_n]:
            nt = row.get("note_preview_trim") or ""
            hl = row.get("headline") or ""
            print(
                f"  - {row.get('tier')} score={row.get('primary_score')} {row.get('profile_url')}"
            )
            print(f"      {hl[:140]} → {nt[:120]}...")
    return 0


def cmd_dispatch(
    *,
    cfg_path: Path,
    headed: bool,
    dry_run: bool,
    browser_channel: str | None,
    tier_filter: str | None,
    max_profiles: int | None,
    session_path: Path,
    allow_live_dispatch: bool = False,
    login_timeout_seconds: int | None = None,
) -> int:
    max_profiles = validate_live_dispatch_max(
        max_profiles,
        dry_run=dry_run,
        option_name="--max",
    )
    cfg = campaign_config_with_overrides(
        load_yaml_config(cfg_path),
        login_timeout_seconds=login_timeout_seconds,
        fast_dry_run=dry_run,
    )
    send_mode = current_send_mode()
    if not dry_run and send_mode == "manual":
        raise SystemExit(
            "Manual LinkedIn send mode is active. Open the profile, copy the "
            "approved note, and record the outcome instead of browser-clicking "
            "from automation. Set LINKEDIN_SEND_MODE=cli_gated only when you "
            "intend to use the CLI approval gate."
        )
    if not dry_run and not allow_live_dispatch:
        raise SystemExit(
            "Live dispatch is blocked by default. Re-run with --dry-run for review "
            "or add --allow-live-dispatch after manually reviewing the queue."
        )
    if not session_path.exists():
        raise SystemExit(
            f"Missing session plan {session_path}. Run: python3 tools/recruiter_orchestrate.py plan …",
        )

    session = json.loads(session_path.read_text(encoding="utf-8"))
    planned_invites = planned_invites_from_session(session)
    queue_objs = session.get("queue") or []
    tuples: list[tuple[str, str]] = []

    tk = tier_filter.strip() if tier_filter else ""
    tier_active = tk and tk.lower() != "all"

    for row in queue_objs:
        if not isinstance(row, dict):
            continue

        if tier_active and (row.get("tier") or "").strip() != tk:
            continue

        canon = lis.canonical_profile_url(row.get("profile_url") or "")
        slug = (
            row.get("search_variant_slug") or row.get("variant_slug_best") or ""
        ).strip()

        if not canon or not slug:
            continue
        tuples.append((canon, slug))
        if max_profiles is not None and len(tuples) >= max_profiles:
            break

    if not tuples:
        if dry_run:
            print("Nothing to dispatch — queue empty after tier/max filters.")
            return 0
        raise SystemExit("Nothing to dispatch — queue empty after tier/max filters.")

    if not dry_run:
        invite_notes = [
            (url, str(planned_invites.get(url, {}).get("note") or ""))
            for url, _slug in tuples
        ]
        gate = can_attempt_live_dispatch(
            invite_notes,
            allow_live_dispatch=allow_live_dispatch,
            db_path=DEFAULT_STATE_DB,
            send_mode=send_mode,
        )
        approval_failures = require_approvals(invite_notes)
        if not gate.allowed:
            preview = "\n".join(
                f"- {f.reason}: {f.profile_url}" for f in approval_failures[:10]
            )
            more = (
                ""
                if len(approval_failures) <= 10
                else f"\n... {len(approval_failures) - 10} more"
            )
            raise SystemExit(
                "Live dispatch requires a matching SQLite approval ledger entry for "
                "each profile and exact note hash. Run:\n"
                "  python3 tools/recruiter_approval.py approve-session "
                f"--session {session_path}\n"
                f"Gate reason: {gate.reason}\n"
                f"Missing approvals:\n{preview or '(none)'}{more}"
            )

    dispatch_args = argparse.Namespace(
        headed=headed,
        dry_run=dry_run,
        scout_jsonl_only=False,
        config=cfg_path,
        max_connections_override=max_profiles,
        variant_filter=None,
        browser_channel=browser_channel,
        allow_live_dispatch=allow_live_dispatch,
    )

    return bot.run_linked_in_campaign_backend(
        dispatch_args,
        cfg,
        queued_override=tuples,
        skip_discovery=True,
        planned_invites=planned_invites,
    )


def cmd_followup(headed: bool, config_path: Path) -> int:
    cli = [
        sys.executable,
        str(TOOLS_DIR / "linkedin_followup.py"),
        "--headed" if headed else "--no-headed",
        "--config",
        str(config_path),
    ]
    return subprocess.call(cli)


def cmd_report() -> int:
    cli = [sys.executable, str(TOOLS_DIR / "recruiter_performance.py")]
    return subprocess.call(cli)


def build_parser() -> argparse.ArgumentParser:
    """Build the stable orchestrator CLI parser."""
    from career_job_search.recruiters.orchestrator_cli import (
        build_parser as _build_parser,
    )

    return _build_parser()


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    parsed = ap.parse_args(argv)
    cfg_path: Path = parsed.config

    if parsed.cmd == "preflight":
        return cmd_preflight(cfg_path, browse_status=parsed.browse_status)

    if parsed.cmd == "scout":
        return cmd_scout(
            config_path=cfg_path,
            headed=parsed.headed,
            browser_channel=parsed.browser_channel,
            variant=parsed.variant,
            sink_path=parsed.action_plan,
            max_profiles_scored=parsed.max_profiles,
            login_timeout_seconds=parsed.login_timeout_seconds,
        )

    if parsed.cmd == "plan":
        retries_first = not parsed.no_retries_first
        return cmd_plan(
            cfg_path,
            tier_filter=parsed.tier_filter,
            retries_first=retries_first,
            mcp_source=parsed.source,
        )

    if parsed.cmd == "dispatch":
        return cmd_dispatch(
            cfg_path=cfg_path,
            headed=parsed.headed,
            dry_run=parsed.dry_run,
            browser_channel=parsed.browser_channel,
            tier_filter=parsed.tier_filter,
            max_profiles=parsed.max_profiles,
            session_path=parsed.session,
            allow_live_dispatch=parsed.allow_live_dispatch,
            login_timeout_seconds=parsed.login_timeout_seconds,
        )

    if parsed.cmd == "followup":
        return cmd_followup(headed=parsed.headed, config_path=cfg_path)

    if parsed.cmd == "report":
        return cmd_report()

    if parsed.cmd == "daily":
        parsed.max_dispatch = validate_live_dispatch_max(
            parsed.max_dispatch,
            dry_run=parsed.dry_run,
            option_name="--max-dispatch",
        )
        if getattr(parsed, "mode", "tier") == "hiring_network":
            cli = [
                sys.executable,
                str(TOOLS_DIR / "hiring_network_workflow.py"),
                "--config",
                str(cfg_path),
                "daily",
                "--headed" if parsed.headed else "--no-headed",
            ]
            if parsed.dry_run:
                cli.append("--dry-run")
            elif parsed.max_dispatch:
                cli.extend(["--auto-send", "--max", str(parsed.max_dispatch)])
            if parsed.variant:
                cli.extend(["--variant", parsed.variant])
            if parsed.browser_channel:
                cli.extend(["--browser-channel", parsed.browser_channel])
            if parsed.allow_live_dispatch:
                cli.append("--allow-live-dispatch")
            return subprocess.call(cli)

        login_timeout_seconds = parsed.login_timeout_seconds
        if parsed.dry_run and login_timeout_seconds is None:
            login_timeout_seconds = 60
        scout_cap = default_daily_scout_cap(
            dry_run=parsed.dry_run,
            max_dispatch=parsed.max_dispatch,
            max_scout=parsed.max_scout,
        )

        rc = cmd_scout(
            config_path=cfg_path,
            headed=parsed.headed,
            browser_channel=parsed.browser_channel,
            variant=parsed.variant,
            sink_path=ACTION_PLAN_JSONL,
            max_profiles_scored=scout_cap,
            login_timeout_seconds=login_timeout_seconds,
            dry_run_context=parsed.dry_run,
        )

        if rc != 0:
            return rc

        rc_plan = cmd_plan(
            cfg_path,
            tier_filter=parsed.tier_filter_plan,
            retries_first=True,
        )

        if rc_plan != 0:
            return rc_plan

        return cmd_dispatch(
            cfg_path=cfg_path,
            headed=parsed.headed,
            dry_run=parsed.dry_run,
            browser_channel=parsed.browser_channel,
            tier_filter=parsed.tier_dispatch,
            max_profiles=parsed.max_dispatch,
            session_path=SESSION_STATE_JSON,
            allow_live_dispatch=parsed.allow_live_dispatch,
            login_timeout_seconds=login_timeout_seconds,
        )

    raise SystemExit(f"Unknown command {parsed.cmd!r}")


if __name__ == "__main__":
    raise SystemExit(main())
