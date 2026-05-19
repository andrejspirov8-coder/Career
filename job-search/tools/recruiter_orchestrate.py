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

from matching_lib import CV_DIR, PROFILES_PATH, load_profiles

import linkedin_selectors as lis
import linkedin_recruiter_bot as bot
from linkedin_browser import browse_debug_port
from linkedin_profile_lock import (
    describe_profile_lock,
    release_stale_chrome_profile_lock,
)
from recruiter_linkedin_paths import (
    ACTION_PLAN_JSONL,
    DEFAULT_LINKEDIN_CONFIG,
    PROFILE_DIR,
    RECRUITERS_CSV,
    SESSION_STATE_JSON,
)

TOOLS_DIR = Path(__file__).resolve().parent


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
        print(f"Profile lock: cleared stale lock (now {describe_profile_lock(PROFILE_DIR)})")
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
) -> int:
    cfg = load_yaml_config(config_path)
    scout_args = argparse.Namespace(
        headed=headed,
        dry_run=False,
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


def cmd_plan(cfg_path: Path, *, tier_filter: str | None, retries_first: bool) -> int:
    cfg = load_yaml_config(cfg_path)
    payload, skips = build_session_queue_payload(cfg, tier_filter=tier_filter, retries_first=retries_first)

    doc = {
        "schema": "recruiter_session_state_v1",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "config_path": str(cfg_path.resolve()),
        "tier_filter": tier_filter,
        "queue": payload,
        "skip_stats": skips,
        "blocked_reason": "",
    }
    SESSION_STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    SESSION_STATE_JSON.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

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
            print(f"  - {row.get('tier')} score={row.get('primary_score')} {row.get('profile_url')}")
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
) -> int:
    cfg = load_yaml_config(cfg_path)
    if not session_path.exists():
        raise SystemExit(
            f"Missing session plan {session_path}. Run: python3 tools/recruiter_orchestrate.py plan …",
        )

    session = json.loads(session_path.read_text(encoding="utf-8"))
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
        slug = (row.get("search_variant_slug") or row.get("variant_slug_best") or "").strip()

        if not canon or not slug:
            continue
        tuples.append((canon, slug))
        if max_profiles is not None and len(tuples) >= max_profiles:
            break

    if not tuples:
        raise SystemExit("Nothing to dispatch — queue empty after tier/max filters.")

    dispatch_args = argparse.Namespace(
        headed=headed,
        dry_run=dry_run,
        scout_jsonl_only=False,
        config=cfg_path,
        max_connections_override=None,
        variant_filter=None,
        browser_channel=browser_channel,
    )

    return bot.run_linked_in_campaign_backend(
        dispatch_args,
        cfg,
        queued_override=tuples,
        skip_discovery=True,
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
    ap = argparse.ArgumentParser(description="Recruiter scout/plan/dispatch orchestrator.")
    ap.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_LINKEDIN_CONFIG,
        help="LinkedIn recruiter YAML config",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--headed",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Show automation browser (--no-headed = headless).",
    )
    shared.add_argument("--browser-channel", default=None)

    pf = sub.add_parser("preflight", help="Validate CV paths + show caps.")
    pf.add_argument("--browse-status", action="store_true", help="Probe Chrome debugger / browse_ws port.")

    scout = sub.add_parser("scout", parents=[shared])
    scout.add_argument("--variant", default=None)
    scout.add_argument(
        "--action-plan",
        type=Path,
        default=ACTION_PLAN_JSONL,
        help="Destination JSONL (default pipeline/recruiter_action_plan.jsonl)",
    )

    pl = sub.add_parser("plan", parents=[shared])
    pl.add_argument(
        "--tier",
        dest="tier_filter",
        default=None,
        help="Only queue rows tagged this tier from JSONL (e.g. tier_1). Omit for full queue.",
    )
    pl.add_argument(
        "--no-retries-first",
        action="store_true",
        help="Do not prepend skipped_no_connect retry URLs.",
    )

    dsp = sub.add_parser("dispatch", parents=[shared])
    dsp.add_argument("--dry-run", action="store_true")
    dsp.add_argument("--tier", dest="tier_filter", default=None)
    dsp.add_argument("--max", dest="max_profiles", type=int, default=None)
    dsp.add_argument(
        "--session",
        type=Path,
        default=SESSION_STATE_JSON,
        help="Session JSON produced by plan (default recruiter_session_state.json)",
    )

    daily = sub.add_parser("daily", parents=[shared])
    daily.add_argument("--dry-run", action="store_true")
    daily.add_argument("--tier", dest="tier_filter_plan", default=None)
    daily.add_argument("--dispatch-tier", dest="tier_dispatch", default=None)
    daily.add_argument("--max-dispatch", type=int, default=None)
    daily.add_argument("--variant", default=None)

    fu = sub.add_parser("followup", parents=[shared])
    rp = sub.add_parser("report")

    return ap


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
        )

    if parsed.cmd == "plan":
        retries_first = not parsed.no_retries_first
        return cmd_plan(cfg_path, tier_filter=parsed.tier_filter, retries_first=retries_first)

    if parsed.cmd == "dispatch":
        return cmd_dispatch(
            cfg_path=cfg_path,
            headed=parsed.headed,
            dry_run=parsed.dry_run,
            browser_channel=parsed.browser_channel,
            tier_filter=parsed.tier_filter,
            max_profiles=parsed.max_profiles,
            session_path=parsed.session,
        )

    if parsed.cmd == "followup":
        return cmd_followup(headed=parsed.headed, config_path=cfg_path)

    if parsed.cmd == "report":
        return cmd_report()

    if parsed.cmd == "daily":
        rc = cmd_scout(
            config_path=cfg_path,
            headed=parsed.headed,
            browser_channel=parsed.browser_channel,
            variant=parsed.variant,
            sink_path=ACTION_PLAN_JSONL,
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
        )

    raise SystemExit(f"Unknown command {parsed.cmd!r}")


if __name__ == "__main__":
    raise SystemExit(main())
