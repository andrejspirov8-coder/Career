"""CSV schema helpers for the three-agent discovery pipeline."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from career_job_search.integrations.linkedin.paths import (
    CANDIDATES_DISCOVERY_CSV,
    CANDIDATES_VALIDATED_CSV,
)

DISCOVERY_HEADER = (
    "profile_url",
    "name",
    "headline",
    "company",
    "location",
    "company_source_url",
    "discovery_source",
    "source_backend",
    "discovery_notes",
    "variant_slug",
    "cv_score",
    "persona",
    "rank_score_draft",
    "search_intent",
    "needs_linkedin_url",
    "discovered_at",
)

VALIDATION_EXTRA_HEADER = (
    "company_relevance_score",
    "company_rationale",
    "company_flags",
    "company_web_url",
    "validation_status",
    "validated_at",
)

ENRICHMENT_EXTRA_HEADER = (
    "enriched_about",
    "enriched_role_text",
    "enriched_at",
)

VALIDATED_HEADER = DISCOVERY_HEADER + VALIDATION_EXTRA_HEADER + ENRICHMENT_EXTRA_HEADER


def blank_discovery_row() -> dict[str, str]:
    return {k: "" for k in DISCOVERY_HEADER}


def blank_validated_row() -> dict[str, str]:
    return {k: "" for k in VALIDATED_HEADER}


def discovery_row_partial(**fields: Any) -> dict[str, str]:
    row = blank_discovery_row()
    for key, value in fields.items():
        if key in row:
            row[key] = "" if value is None else str(value)
    return row


def validated_row_partial(**fields: Any) -> dict[str, str]:
    row = blank_validated_row()
    for key, value in fields.items():
        if key in row:
            row[key] = "" if value is None else str(value)
    return row


def ensure_csv_schema(csv_path: Path, header: tuple[str, ...]) -> None:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return
    with csv_path.open(encoding="utf-8", newline="") as fh:
        first = fh.readline()
    if not first.strip():
        return
    old_fields = next(csv.reader([first]))
    if list(old_fields) == list(header):
        return
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    merged = [{k: str(row.get(k, "") or "") for k in header} for row in rows]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(header))
        writer.writeheader()
        writer.writerows(merged)


def read_csv_rows(csv_path: Path, header: tuple[str, ...]) -> list[dict[str, str]]:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return []
    ensure_csv_schema(csv_path, header)
    with csv_path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv_rows(
    csv_path: Path, header: tuple[str, ...], rows: list[dict[str, str]]
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(header))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: str(row.get(k, "") or "") for k in header})


def append_csv_rows(
    csv_path: Path, header: tuple[str, ...], rows: list[dict[str, str]]
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(header))
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: str(row.get(k, "") or "") for k in header})


def read_discovery_rows(
    csv_path: Path = CANDIDATES_DISCOVERY_CSV,
) -> list[dict[str, str]]:
    return read_csv_rows(csv_path, DISCOVERY_HEADER)


def read_validated_rows(
    csv_path: Path = CANDIDATES_VALIDATED_CSV,
) -> list[dict[str, str]]:
    return read_csv_rows(csv_path, VALIDATED_HEADER)


def write_discovery_rows(
    rows: list[dict[str, str]], csv_path: Path = CANDIDATES_DISCOVERY_CSV
) -> None:
    write_csv_rows(csv_path, DISCOVERY_HEADER, rows)


def write_validated_rows(
    rows: list[dict[str, str]], csv_path: Path = CANDIDATES_VALIDATED_CSV
) -> None:
    write_csv_rows(csv_path, VALIDATED_HEADER, rows)


def discovery_to_validated(row: dict[str, str]) -> dict[str, str]:
    out = blank_validated_row()
    for key in DISCOVERY_HEADER:
        out[key] = str(row.get(key, "") or "")
    return out


def sort_by_rank_score(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    def key(row: dict[str, str]) -> float:
        try:
            return float(row.get("rank_score_draft") or 0)
        except ValueError:
            return 0.0

    return sorted(rows, key=key, reverse=True)


def today_iso() -> str:
    return date.today().isoformat()
