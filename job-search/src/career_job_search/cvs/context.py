"""Compact CV context for local recruiter assistance."""

from __future__ import annotations

from functools import lru_cache

from career_job_search.core.paths import project_path
from career_job_search.cvs.catalogue import load_cv_catalogue

TRACK_SUMMARY = (
    "Candidate tracks: luxury-retail, luxury-retail-lt, operations-management, "
    "it-business. Geography: Vilnius/Lithuania/Baltics. Target hiring leaders in "
    "premium retail, multi-site ops, or IT support — not generic staffing/pharma/finance."
)


@lru_cache(maxsize=1)
def cv_context_blob() -> str:
    lines: list[str] = []
    for variant in load_cv_catalogue().variants:
        lines.append(
            f"{variant.slug}: titles={variant.target_titles[:4]} "
            f"keywords={variant.keywords[:12]}"
        )
        source = project_path("cv", variant.source_filename)
        if source.is_file():
            excerpt = source.read_text(encoding="utf-8")[:400].replace("\n", " ")
            lines.append(f"  excerpt: {excerpt[:400]}")
    return "\n".join(lines) if lines else TRACK_SUMMARY
