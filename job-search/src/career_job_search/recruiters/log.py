"""CSV helpers for recruiter pipeline (audit log schema)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from career_job_search.integrations.linkedin.paths import RECRUITERS_CSV

CSV_HEADER = (
    "date_iso",
    "profile_url",
    "name",
    "headline",
    "variant_slug",
    "primary_score",
    "runner_up_slug",
    "runner_up_score",
    "margin_over_second",
    "top_signals",
    "connect_path",
    "confidence",
    "status",
    "skip_reason",
    "note_preview",
    "accepted_at",
    "withdraw_or_pending",
    "reply_at",
    "reply_excerpt",
    "interview_at",
    "persona",
    "rank_score",
    "profile_confidence",
    "safety_decision",
    "note_reason",
    "final_note",
)


def blank_recruiter_row() -> dict[str, Any]:
    return {k: "" for k in CSV_HEADER}


def recruiter_row_partial(**fields: Any) -> dict[str, Any]:
    row = blank_recruiter_row()
    for k, v in fields.items():
        if k in row:
            row[k] = "" if v is None else str(v)
    return row


def ensure_recruiter_csv_schema(csv_path: Path = RECRUITERS_CSV) -> None:
    """Upgrade recruiters.csv header in-place when new columns are added."""
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return
    with csv_path.open(encoding="utf-8", newline="") as f:
        first = f.readline()
    if not first.strip():
        return
    old_fields = next(csv.reader([first]))
    if list(old_fields) == list(CSV_HEADER):
        return
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    merged: list[dict[str, str]] = []
    for row in rows:
        clean = {k: str(row.get(k, "") or "") for k in CSV_HEADER}
        merged.append(clean)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(CSV_HEADER))
        w.writeheader()
        w.writerows(merged)


def append_recruiter_row(row: dict[str, Any], csv_path: Path = RECRUITERS_CSV) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(CSV_HEADER))
        if write_header:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in CSV_HEADER})
