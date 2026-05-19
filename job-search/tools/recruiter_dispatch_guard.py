"""Pre-dispatch guards: stub URLs, empty identity, already-sent dedupe."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import linkedin_selectors as lis
from recruiter_linkedin_paths import RECRUITERS_CSV

_STUB_URL_RE = re.compile(
    r"linkedin\.com/in/(sample|test|demo|example|jane-doe)[-/]",
    re.I,
)

_ALREADY_SENT_STATUSES = frozenset({"sent", "pending", "accepted"})


def is_stub_or_empty_row(row: dict[str, Any]) -> tuple[bool, str]:
    """Return (should_skip, reason)."""
    url = str(row.get("profile_url") or "")
    source = str(row.get("source_backend") or row.get("discovery_source") or "")
    if source == "offline_stub":
        return True, "offline_stub"
    if _STUB_URL_RE.search(url):
        return True, "stub_url"
    name = str(row.get("name") or "").strip()
    headline = str(row.get("headline") or "").strip()
    company = str(row.get("company") or "").strip()
    if not name and not headline and not company:
        return True, "empty_identity"
    return False, ""


def load_already_sent_urls(csv_path: Path | None = None) -> set[str]:
    path = csv_path or RECRUITERS_CSV
    urls: set[str] = set()
    if not path.is_file():
        return urls
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            status = (row.get("status") or "").strip().lower()
            if status not in _ALREADY_SENT_STATUSES:
                continue
            canon = lis.canonical_profile_url(row.get("profile_url") or "")
            if canon:
                urls.add(canon)
    return urls
