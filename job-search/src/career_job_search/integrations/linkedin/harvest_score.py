#!/usr/bin/env python3
"""Score harvested LinkedIn profile stubs and append pipeline rows.

Usage (from job-search/):
  python3 -m career_job_search.integrations.linkedin.harvest_score --stdin
  python3 -m career_job_search.integrations.linkedin.harvest_score pipeline/mcp_discovery_batch.jsonl
  python3 -m career_job_search.integrations.linkedin.harvest_score pipeline/mcp_discovery_batch.jsonl --write-action-plan
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml

from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.campaign_config import (
    cfg_matching,
    read_seen_profile_urls,
    read_skip_revisit_urls,
)
from career_job_search.integrations.linkedin.paths import (
    ACTION_PLAN_JSONL,
    DEFAULT_LINKEDIN_CONFIG,
    MCP_DISCOVERY_BATCH_JSONL,
    RECRUITERS_CSV,
)
from career_job_search.recruiters.log import (
    append_recruiter_row,
    ensure_recruiter_csv_schema,
    recruiter_row_partial,
)
from career_job_search.recruiters.matching import (
    match_recruiter_profile,
    should_send_recruiter_connection,
)


def load_cfg(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def note_for_variant(cfg: dict, slug: str, first_name: str) -> str:
    templates = cfg.get("connection_notes") or {}
    tpl = templates.get(slug) or ""
    fn = first_name.split()[0] if first_name else "there"
    return tpl.replace("{first_name}", fn).strip()


def stub_to_scout_record(
    stub: dict[str, str], *, today: str, cfg: dict
) -> dict[str, object]:
    """Build a scout-shaped JSONL row from an MCP harvest stub."""
    url = (stub.get("profile_url") or "").strip()
    canon = lis.canonical_profile_url(url) or url
    name = (stub.get("name") or "").strip()
    headline = (stub.get("headline") or "").strip()
    company = (stub.get("company") or "").strip()
    about = (stub.get("about") or "").strip()
    role_text = (stub.get("role_text") or "").strip()
    location = (stub.get("location") or "").strip()
    variant = (stub.get("variant_slug") or "luxury-retail").strip()

    scoring = match_recruiter_profile(
        headline=headline or name or "recruiter",
        name=name,
        profile_url=canon,
        company=company,
        about=about,
        role_text=role_text,
        location=location,
        recruiter_cfg=cfg,
    )
    matcher = cfg_matching(cfg)
    rec = scoring.get("recommendation") or {}
    meta = scoring.get("recruiter_meta") or {}
    best = (rec.get("variant_slug") or variant).strip()
    okay, refusal = should_send_recruiter_connection(
        scoring,
        min_primary_score=float(matcher.get("min_primary_score", 12)),
        min_margin_over_second=float(matcher.get("min_margin_over_second", 4.0)),
        require_clear_winner=bool(matcher.get("require_clear_winner", False)),
        require_recruiter_gate=bool(matcher.get("require_recruiter_gate", True)),
        full_cfg=cfg,
    )
    return {
        "schema": "linkedin_recruit_scout_v1",
        "source": "mcp_discovery",
        "date_iso": today,
        "profile_url": canon,
        "name": name,
        "headline": headline,
        "company_guess": company,
        "location": location,
        "about": about[:420],
        "role_text": role_text[:420],
        "search_variant_slug": variant,
        "search_intent": stub.get("search_intent") or "",
        "variant_slug_best": best,
        "primary_score": rec.get("primary_score"),
        "margin_over_second": rec.get("margin_over_second"),
        "confidence": rec.get("confidence"),
        "recruiter_gate_ok": meta.get("recruiter_gate_ok"),
        "would_send_under_matching_rules": okay,
        "matching_refusal": refusal,
        "top_signals": meta.get("top_signals") or "",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="JSONL stubs (default pipeline/mcp_discovery_batch.jsonl)",
    )
    ap.add_argument("--config", type=Path, default=DEFAULT_LINKEDIN_CONFIG)
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument(
        "--write-action-plan",
        action="store_true",
        help=f"Also append scout rows to {ACTION_PLAN_JSONL.name}",
    )
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    today = date.today().isoformat()
    ensure_recruiter_csv_schema(RECRUITERS_CSV)
    seen = read_seen_profile_urls(RECRUITERS_CSV)
    skip_revisit = read_skip_revisit_urls(RECRUITERS_CSV)

    lines: list[str] = []
    if args.stdin:
        lines = sys.stdin.read().splitlines()
    elif args.input:
        lines = args.input.read_text(encoding="utf-8").splitlines()
    elif MCP_DISCOVERY_BATCH_JSONL.is_file():
        lines = MCP_DISCOVERY_BATCH_JSONL.read_text(encoding="utf-8").splitlines()
    else:
        ap.error(
            "Provide input file, --stdin, or create pipeline/mcp_discovery_batch.jsonl"
        )

    n_new = n_connect = 0
    if args.write_action_plan:
        ACTION_PLAN_JSONL.parent.mkdir(parents=True, exist_ok=True)

    for line in lines:
        line = line.strip()
        if not line:
            continue
        stub = json.loads(line)
        url = (stub.get("profile_url") or "").strip()
        canon = lis.canonical_profile_url(url) or url
        if not canon or "/in/" not in canon:
            continue
        if canon in seen or canon in skip_revisit:
            continue

        scout_row = stub_to_scout_record(stub, today=today, cfg=cfg)
        if args.write_action_plan:
            with ACTION_PLAN_JSONL.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(scout_row, ensure_ascii=False) + "\n")

        variant = str(
            scout_row.get("variant_slug_best")
            or stub.get("variant_slug")
            or "luxury-retail"
        )
        name = str(stub.get("name") or "")
        headline = str(stub.get("headline") or "")
        okay = bool(scout_row.get("would_send_under_matching_rules"))
        refusal = str(scout_row.get("matching_refusal") or "")
        rec_confidence = str(scout_row.get("confidence") or "")
        primary = scout_row.get("primary_score", 0)
        note = note_for_variant(cfg, variant, name) if okay else ""

        append_recruiter_row(
            {
                **recruiter_row_partial(
                    date_iso=today,
                    profile_url=canon,
                    name=name,
                    headline=headline,
                    variant_slug=variant,
                    primary_score=str(primary),
                    runner_up_slug="",
                    runner_up_score="",
                    margin_over_second=str(scout_row.get("margin_over_second") or ""),
                    top_signals=str(scout_row.get("top_signals") or "")[:200],
                    confidence=rec_confidence,
                ),
                "status": "dry_run_would_connect" if okay else "dry_run_would_skip",
                "skip_reason": "" if okay else refusal,
                "note_preview": note[:220] if okay else "",
            }
        )
        seen.add(canon)
        n_new += 1
        if okay:
            n_connect += 1
        print(
            f"{scout_row.get('would_send_under_matching_rules')}\t{primary}\t{variant}\t{name or canon}\t{refusal if not okay else note[:60]}"
        )

    print(f"Appended {n_new} rows ({n_connect} would_connect)", flush=True)
    if args.write_action_plan:
        print(f"Scout rows appended to {ACTION_PLAN_JSONL}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
