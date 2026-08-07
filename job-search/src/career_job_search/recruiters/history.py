"""Read-only recruiter outcome lookups shared by agent contexts and tools."""

from __future__ import annotations

import csv
from pathlib import Path

from career_job_search.core.paths import project_path

DEFAULT_RECRUITERS_CSV = project_path("pipeline", "recruiters.csv")


def company_history(
    company: str,
    *,
    recruiters_csv: Path = DEFAULT_RECRUITERS_CSV,
) -> dict[str, int | str]:
    company_key = company.strip().lower()
    sent = accepted = 0
    last_at = ""
    if not company_key or not recruiters_csv.is_file():
        return {"sent": 0, "accepted": 0, "last_contact_at": ""}
    with recruiters_csv.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            row_company = (row.get("company") or row.get("company_guess") or "").lower()
            if company_key not in row_company and row_company not in company_key:
                continue
            status = (row.get("status") or "").strip().lower()
            if status in {"sent", "pending", "accepted"}:
                sent += 1
            if (row.get("accepted_at") or "").strip():
                accepted += 1
            timestamp = (row.get("date") or row.get("sent_at") or "").strip()
            if timestamp > last_at:
                last_at = timestamp
    return {"sent": sent, "accepted": accepted, "last_contact_at": last_at}
