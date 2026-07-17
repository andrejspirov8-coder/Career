#!/usr/bin/env python3
"""Approve or check recruiter session plans before live LinkedIn dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_job_search.recruiters.repository import (
    DEFAULT_STATE_DB,
    approval_check,
    approve_invite,
    canonical_profile_url,
    count_by_status,
    init_db,
)

DEFAULT_SESSION = Path("pipeline/recruiter_session_state.json")


def _run_id(prefix: str = "manual") -> str:
    stamp = datetime.now(UTC).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}"


def _load_session_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Missing session plan: {path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc.get("queue") or []
    if not isinstance(rows, list):
        raise SystemExit("Session plan queue must be a list.")
    return [r for r in rows if isinstance(r, dict)]


def _row_note(row: dict[str, Any]) -> str:
    return str(row.get("note_live_full") or row.get("note") or "").strip()


def cmd_init(args: argparse.Namespace) -> int:
    db = init_db(Path(args.db))
    print(f"Initialized approval database: {db}")
    return 0


def cmd_approve_session(args: argparse.Namespace) -> int:
    rows = _load_session_rows(Path(args.session))
    run_id = args.run_id or _run_id("approval")
    approved = 0
    skipped = 0
    limit = args.limit
    for row in rows:
        url = canonical_profile_url(str(row.get("profile_url") or ""))
        note = _row_note(row)
        if not url or not note:
            skipped += 1
            continue
        approve_invite(
            profile_url=url,
            note=note,
            run_id=run_id,
            approved_by=args.approved_by,
            score=_coerce_float(row.get("primary_score") or row.get("rank_score")),
            tier=str(row.get("tier") or ""),
            metadata=row,
            db_path=Path(args.db),
        )
        approved += 1
        if limit is not None and approved >= limit:
            break
    print(
        f"Approved {approved} invite(s) from {args.session}; skipped={skipped}; run_id={run_id}"
    )
    return 0


def _coerce_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def cmd_check_session(args: argparse.Namespace) -> int:
    rows = _load_session_rows(Path(args.session))
    failures = []
    checked = 0
    for row in rows:
        url = canonical_profile_url(str(row.get("profile_url") or ""))
        note = _row_note(row)
        if not url or not note:
            failures.append((url or "(missing url)", "missing_profile_or_note"))
            continue
        checked += 1
        check = approval_check(profile_url=url, note=note, db_path=Path(args.db))
        if not check.approved:
            failures.append((check.profile_url, check.reason))
    if failures:
        print(f"Approval check failed: {len(failures)} problem(s) / {checked} checked")
        for url, reason in failures[:25]:
            print(f"- {reason}: {url}")
        if len(failures) > 25:
            print(f"... {len(failures) - 25} more")
        return 2
    print(f"Approval check passed: {checked} invite(s) approved")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    stats = count_by_status(Path(args.db))
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=str(DEFAULT_STATE_DB))
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    approve = sub.add_parser("approve-session")
    approve.add_argument("--session", default=str(DEFAULT_SESSION))
    approve.add_argument("--approved-by", default="local_operator")
    approve.add_argument("--run-id", default="")
    approve.add_argument("--limit", type=int, default=None)

    check = sub.add_parser("check-session")
    check.add_argument("--session", default=str(DEFAULT_SESSION))

    sub.add_parser("report")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "approve-session":
        return cmd_approve_session(args)
    if args.cmd == "check-session":
        return cmd_check_session(args)
    if args.cmd == "report":
        return cmd_report(args)
    raise SystemExit(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
