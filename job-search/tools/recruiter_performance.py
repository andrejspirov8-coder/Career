#!/usr/bin/env python3
"""
Weekly funnel stats from pipeline/recruiters.csv (LinkedIn recruiter automation).

Usage (from job-search/):

  python3 tools/recruiter_performance.py
  python3 tools/recruiter_performance.py --csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
JOB_ROOT = TOOLS_DIR.parent
RECRUITERS_CSV = JOB_ROOT / "pipeline" / "recruiters.csv"


def load_recruiters() -> list[dict[str, str]]:
    if not RECRUITERS_CSV.exists():
        return []
    with RECRUITERS_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _normalize_note_key(note: str, max_len: int = 72) -> str:
    s = re.sub(r"\s+", " ", (note or "").strip())
    return s[:max_len] if s else ""


def analyse_note_previews(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """
    Roll up `note_preview` for rows with status=sent (rough outcome correlation).
    """
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {"sent": 0, "accepted": 0, "reply": 0}
    )
    for row in rows:
        if (row.get("status") or "").strip() != "sent":
            continue
        key = _normalize_note_key(row.get("note_preview") or "")
        if not key:
            key = "(empty note_preview)"
        b = buckets[key]
        b["sent"] += 1
        if (row.get("accepted_at") or "").strip():
            b["accepted"] += 1
        if (row.get("reply_at") or "").strip():
            b["reply"] += 1
    out: list[dict[str, Any]] = []
    for phrase, b in sorted(buckets.items(), key=lambda x: (-x[1]["sent"], x[0])):
        s = b["sent"]
        out.append(
            {
                "note_first_line": phrase,
                "sent": s,
                "accepted": b["accepted"],
                "reply": b["reply"],
                "accept_rate": (b["accepted"] / s) if s else 0.0,
                "reply_rate": (b["reply"] / s) if s else 0.0,
            }
        )
    return out


def analyse_by_variant(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Aggregate sent / accepted / reply / interview per variant_slug."""
    stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for row in rows:
        variant = (row.get("variant_slug") or "").strip()
        if not variant or variant.startswith("__meta__"):
            continue
        status = (row.get("status") or "").strip()
        stats[variant]["rows"] += 1
        if status == "sent":
            stats[variant]["sent"] += 1
        if (row.get("accepted_at") or "").strip():
            stats[variant]["accepted"] += 1
        if (row.get("reply_at") or "").strip():
            stats[variant]["reply"] += 1
        if (row.get("interview_at") or "").strip():
            stats[variant]["interview"] += 1

    out: dict[str, dict[str, Any]] = {}
    for variant, counts in sorted(stats.items()):
        sent = int(counts.get("sent", 0))
        accepted = int(counts.get("accepted", 0))
        reply = int(counts.get("reply", 0))
        interview = int(counts.get("interview", 0))
        out[variant] = {
            "profiles_logged": int(counts.get("rows", 0)),
            "sent": sent,
            "accepted": accepted,
            "reply": reply,
            "interview": interview,
            "accept_rate": (accepted / sent) if sent else 0.0,
            "reply_rate": (reply / sent) if sent else 0.0,
            "interview_rate": (interview / sent) if sent else 0.0,
        }
    return out


def print_note_preview_table(rollup: list[dict[str, Any]], *, limit: int = 12) -> None:
    if not rollup:
        return
    print("\n" + "=" * 100)
    print("NOTE PREVIEW ROLLUP (sent rows only — first ~72 chars of note_preview)")
    print("=" * 100)
    print(f"{'Note opening':<72} {'Snt':>4} {'Acc%':>7} {'Rep%':>7}")
    print("-" * 100)
    for row in rollup[:limit]:
        note = (row["note_first_line"] or "")[:72]
        print(
            f"{note:<72} "
            f"{row['sent']:>4} "
            f"{row['accept_rate']:>6.1%} "
            f"{row['reply_rate']:>6.1%}"
        )
    if len(rollup) > limit:
        print(f"... ({len(rollup) - limit} more distinct note shapes not shown)")
    print()


def print_csv_notes(rollup: list[dict[str, Any]]) -> None:
    print("note_first_line,sent,accepted,reply,accept_rate,reply_rate")
    for row in rollup:
        nl = (row["note_first_line"] or "").replace('"', '""')
        print(
            f'"{nl}",{row["sent"]},{row["accepted"]},{row["reply"]},'
            f'{row["accept_rate"]:.4f},{row["reply_rate"]:.4f}'
        )


def print_table(results: dict[str, dict[str, Any]]) -> None:
    print("\n" + "=" * 96)
    print("LINKEDIN RECRUITER FUNNEL BY CV VARIANT")
    print("=" * 96)
    print(
        f"{'Variant':<28} {'Rows':>6} {'Sent':>6} {'Acc%':>7} {'Rep%':>7} {'Int%':>7}"
    )
    print("-" * 96)
    for variant in sorted(results.keys()):
        d = results[variant]
        print(
            f"{variant:<28} "
            f"{d['profiles_logged']:>6} "
            f"{d['sent']:>6} "
            f"{d['accept_rate']:>6.1%} "
            f"{d['reply_rate']:>6.1%} "
            f"{d['interview_rate']:>6.1%}"
        )
    print(
        "\nRates use **sent** as the denominator. Fill interview_at manually after recruiter calls.\n"
    )


def print_csv(results: dict[str, dict[str, Any]]) -> None:
    print(
        "variant_slug,profiles_logged,sent,accepted,reply,interview,accept_rate,reply_rate,interview_rate"
    )
    for variant in sorted(results.keys()):
        d = results[variant]
        print(
            f"{variant},{d['profiles_logged']},{d['sent']},{d['accepted']},{d['reply']},"
            f"{d['interview']},{d['accept_rate']:.4f},{d['reply_rate']:.4f},{d['interview_rate']:.4f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse LinkedIn recruiter CSV funnel.")
    parser.add_argument("--csv", action="store_true", help="Machine-readable CSV output")
    parser.add_argument(
        "--notes-csv",
        action="store_true",
        help="With --csv, output note_preview rollup instead of variant rollup",
    )
    args = parser.parse_args()

    rows = load_recruiters()
    if not rows:
        print(f"No data in {RECRUITERS_CSV}", file=sys.stderr)
        sys.exit(0)

    if args.csv and args.notes_csv:
        rollup = analyse_note_previews(rows)
        print_csv_notes(rollup)
        return

    results = analyse_by_variant(rows)
    if args.csv:
        print_csv(results)
    else:
        print_table(results)
        print_note_preview_table(analyse_note_previews(rows))


if __name__ == "__main__":
    main()
