"""Bridge validated discovery CSV rows into scout JSONL for rank/dispatch."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.integrations.linkedin.harvest_score import stub_to_scout_record
from career_job_search.integrations.linkedin.paths import (
    ACTION_PLAN_JSONL,
    CANDIDATES_VALIDATED_CSV,
    DEFAULT_LINKEDIN_CONFIG,
)
from career_job_search.recruiters.discovery_csv import read_validated_rows


def load_cfg(path: Path) -> dict:
    import yaml

    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def validated_row_to_stub(row: dict[str, str]) -> dict[str, str]:
    about = (row.get("enriched_about") or row.get("discovery_notes") or "").strip()
    role_text = (row.get("enriched_role_text") or "").strip()
    return {
        "profile_url": row.get("profile_url") or "",
        "name": row.get("name") or "",
        "headline": row.get("headline") or "",
        "company": row.get("company") or "",
        "location": row.get("location") or "",
        "variant_slug": row.get("variant_slug") or "luxury-retail",
        "search_intent": row.get("search_intent") or "hiring_leader",
        "about": about,
        "role_text": role_text,
    }


def rows_for_bridge(
    rows: list[dict[str, str]], *, include_review: bool = True
) -> list[dict[str, str]]:
    allowed = {"approved", "review"} if include_review else {"approved"}
    out: list[dict[str, str]] = []
    for row in rows:
        status = (row.get("validation_status") or "").strip().lower()
        if status not in allowed:
            continue
        url = (
            lis.canonical_profile_url(row.get("profile_url") or "")
            or (row.get("profile_url") or "").strip()
        )
        if not url or "/in/" not in url:
            continue
        if (row.get("needs_linkedin_url") or "").strip().lower() in {
            "true",
            "1",
            "yes",
        }:
            continue
        out.append({**row, "profile_url": url})
    return out


def validated_to_scout_records(
    rows: list[dict[str, str]], *, cfg: dict, today: str | None = None
) -> list[dict[str, object]]:
    today = today or date.today().isoformat()
    records: list[dict[str, object]] = []
    for row in rows:
        stub = validated_row_to_stub(row)
        scout = stub_to_scout_record(stub, today=today, cfg=cfg)
        scout["source"] = "validated_csv"
        scout["source_backend"] = (
            row.get("source_backend") or row.get("discovery_source") or ""
        )
        scout["company_guess"] = row.get("company") or scout.get("company_guess")
        if row.get("company_relevance_score"):
            scout["company_relevance_score"] = row.get("company_relevance_score")
        if row.get("validation_status"):
            scout["validation_status"] = row.get("validation_status")
        if row.get("company_flags"):
            scout["company_flags"] = row.get("company_flags")
        if row.get("company_rationale"):
            scout["company_rationale"] = row.get("company_rationale")
        if row.get("enriched_about"):
            scout["about"] = row.get("enriched_about")
            scout["scraped_about_excerpt"] = str(row.get("enriched_about") or "")[:420]
        if row.get("enriched_role_text"):
            scout["role_text"] = row.get("enriched_role_text")
        if row.get("persona"):
            scout["discovery_persona"] = row.get("persona")
        notes = (row.get("discovery_notes") or "").strip()
        if notes:
            first_line = notes.splitlines()[0].strip().lstrip("#").strip()
            if first_line:
                scout["discovery_persona_evidence"] = first_line[:200]
        records.append(scout)
    return records


def append_scout_records(records: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Bridge validated CSV rows to scout action plan JSONL"
    )
    ap.add_argument(
        "--input",
        type=Path,
        default=CANDIDATES_VALIDATED_CSV,
        help="Validated candidates CSV",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=ACTION_PLAN_JSONL,
        help="Scout action plan JSONL",
    )
    ap.add_argument("--config", type=Path, default=DEFAULT_LINKEDIN_CONFIG)
    ap.add_argument(
        "--approved-only",
        action="store_true",
        help="Skip validation_status=review rows",
    )
    ap.add_argument(
        "--write-action-plan",
        action="store_true",
        help="Append scout records to action plan JSONL",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    rows = read_validated_rows(args.input)
    bridged = rows_for_bridge(rows, include_review=not args.approved_only)
    records = validated_to_scout_records(bridged, cfg=cfg)

    print(f"Validated rows: {len(rows)}")
    print(f"Bridgeable rows: {len(bridged)}")
    for record in records[:10]:
        print(
            f"- {record.get('profile_url')} "
            f"score={record.get('primary_score')} "
            f"variant={record.get('variant_slug_best')}"
        )

    if args.write_action_plan and not args.dry_run:
        append_scout_records(records, args.output)
        print(f"Appended {len(records)} scout row(s) to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
