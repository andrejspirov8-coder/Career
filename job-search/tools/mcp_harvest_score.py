#!/usr/bin/env python3
"""Score harvested LinkedIn profile stubs and append pipeline rows.

Usage (from job-search/):
  python3 tools/mcp_harvest_score.py --stdin   # JSON lines: profile_url, name, headline, variant_slug
  python3 tools/mcp_harvest_score.py harvest.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import linkedin_selectors as lis
from linkedin_recruiter_bot import (
    cfg_matching,
    ensure_recruiter_csv_schema,
    read_seen_profile_urls,
    read_skip_revisit_urls,
)
from recruiter_linkedin_paths import DEFAULT_LINKEDIN_CONFIG, RECRUITERS_CSV
from recruiter_log import append_recruiter_row, recruiter_row_partial
from recruiter_match import match_recruiter_profile, should_send_recruiter_connection


def load_cfg(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def note_for_variant(cfg: dict, slug: str, first_name: str) -> str:
    templates = cfg.get("connection_notes") or {}
    tpl = templates.get(slug) or ""
    fn = first_name.split()[0] if first_name else "there"
    return tpl.replace("{first_name}", fn).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", type=Path, help="JSONL with profile_url, name, headline, variant_slug")
    ap.add_argument("--config", type=Path, default=DEFAULT_LINKEDIN_CONFIG)
    ap.add_argument("--stdin", action="store_true")
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    matcher = cfg_matching(cfg)
    today = date.today().isoformat()
    ensure_recruiter_csv_schema(RECRUITERS_CSV)
    seen = read_seen_profile_urls(RECRUITERS_CSV)
    skip_revisit = read_skip_revisit_urls(RECRUITERS_CSV)

    lines: list[str] = []
    if args.stdin:
        lines = sys.stdin.read().splitlines()
    elif args.input:
        lines = args.input.read_text(encoding="utf-8").splitlines()
    else:
        ap.error("Provide input file or --stdin")

    n_new = n_connect = 0
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
        variant = (stub.get("variant_slug") or "luxury-retail").strip()
        name = (stub.get("name") or "").strip()
        headline = (stub.get("headline") or "").strip()
        scoring = match_recruiter_profile(
            headline=headline or name or "recruiter",
            name=name,
            profile_url=canon,
            company=(stub.get("company") or "").strip(),
            about=(stub.get("about") or "").strip(),
            role_text=(stub.get("role_text") or "").strip(),
            location=(stub.get("location") or "").strip(),
            recruiter_cfg=cfg,
        )
        rec = scoring.get("recommendation") or {}
        meta = scoring.get("recruiter_meta") or {}
        best = (rec.get("variant_slug") or variant).strip()
        primary = rec.get("primary_score", 0)
        runner = scoring.get("runner_up") or {}
        okay, refusal = should_send_recruiter_connection(
            scoring,
            min_primary_score=float(matcher.get("min_primary_score", 12)),
            min_margin_over_second=float(matcher.get("min_margin_over_second", 4.0)),
            require_clear_winner=bool(matcher.get("require_clear_winner", False)),
            require_recruiter_gate=bool(matcher.get("require_recruiter_gate", True)),
        )
        confidence = rec.get("confidence") or ""
        note = note_for_variant(cfg, best, name)
        status = "dry_run_would_connect" if okay else "dry_run_would_skip"
        if okay:
            n_connect += 1
        append_recruiter_row(
            {
                **recruiter_row_partial(
                    date_iso=today,
                    profile_url=canon,
                    name=name,
                    headline=headline,
                    variant_slug=best,
                    primary_score=str(primary),
                    runner_up_slug=(runner.get("variant_slug") or ""),
                    runner_up_score=str(runner.get("primary_score") or ""),
                    margin_over_second=str(rec.get("margin_over_second") or ""),
                    top_signals=",".join(rec.get("top_signals") or [])[:200],
                    confidence=confidence,
                ),
                "status": status,
                "skip_reason": "" if okay else refusal,
                "note_preview": note[:220] if okay else "",
            }
        )
        seen.add(canon)
        n_new += 1
        print(f"{status}\t{primary}\t{best}\t{name or canon}\t{refusal if not okay else note[:60]}")

    print(f"Appended {n_new} rows ({n_connect} would_connect)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
