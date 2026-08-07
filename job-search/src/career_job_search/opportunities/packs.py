"""Shared helpers for building job application packs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from career_job_search.cvs.matching import (
    CV_DIR,
    keyword_gaps,
    matching_result_json,
    pdf_paths_for_slug,
)


def render_readme(pdf_visual: Path, pdf_ats: Path, md_src: Path) -> str:
    return f"""Application pack (assistive — you submit manually)
==============================================

## Checklist before you apply

1. Variant sanity: does the recommended slug match how you want to position yourself?
2. Files: upload `*-ats.pdf` to ATS portals; prefer the visual PDF when emailing a human.
3. Metrics: anything you cite must match `cv/CV_METRICS_INTAKE.md` (do not invent numbers).
4. Optional: skim LinkedIn headline vs target title on the CV variant you chose.
5. Submit yourself on the employer site or board (no auto-submit from this toolkit).
6. Log the application with match score, confidence, salary range, tailored_cv, and response_date when available.

## Suggested artefacts (absolute paths)

- ATS PDF:       {pdf_ats.resolve()}
- Visual PDF:    {pdf_visual.resolve()}
- Markdown src:  {md_src.resolve()}

## Workflow

After any CV edit:

  python cv/build_cv_pdf.py --all

See `README.md` in the job-search folder for the full loop.
"""


def render_keyword_gaps_md(
    slug: str, gaps: list[tuple[str, int]], notes: list[str]
) -> str:
    lines = [
        "# Keyword gaps (suggested additions to review)",
        "",
        f"Recommended CV variant slug: `{slug}`",
        "",
        "These terms appear often in the job description but were not found as tokens in",
        "that variant’s Markdown CV. Consider weaving in **only what is truthful**.",
        "",
    ]
    for note in notes:
        lines.append(f"- {note}")
    lines.extend(
        [
            "",
            "| Suggested token (from JD) | Approx. occurrences |",
            "| --- | ---: |",
        ]
    )
    if gaps:
        for tok, cnt in gaps:
            lines.append(f"| {tok} | {cnt} |")
    else:
        lines.append("| *(no standout gaps detected by this heuristic)* | |")
    lines.append("")
    return "\n".join(lines)


def write_pack_files(
    result: dict[str, Any],
    pack_id: str,
    pack_dir: Path,
    variants: dict[str, Any],
    *,
    overwrite: bool = False,
) -> dict[str, str]:
    """Write README, MATCH.json, KEYWORD_GAPS.md, and job_input.txt."""
    if pack_dir.exists() and not overwrite:
        raise FileExistsError(f"Pack directory already exists: {pack_dir}")

    pack_dir.mkdir(parents=True, exist_ok=True)

    job_data = result["job"]
    rec = result["recommendation"]
    chosen_slug = rec["variant_slug"]
    pdf_info = pdf_paths_for_slug(chosen_slug, variants)
    md_src = CV_DIR / variants[chosen_slug]["markdown"]

    pack_data = dict(result)
    pack_data["pack"] = {
        "job_id": pack_id,
        "recommended_variant_slug": chosen_slug,
        "pdf_visual_path": str(pdf_info["visual"].resolve()),
        "pdf_ats_path": str(pdf_info["ats"].resolve()),
        "markdown_cv_path": str(md_src.resolve()),
    }

    (pack_dir / "README.txt").write_text(
        render_readme(pdf_info["visual"], pdf_info["ats"], md_src),
        encoding="utf-8",
    )
    (pack_dir / "MATCH.json").write_text(
        matching_result_json(pack_data),
        encoding="utf-8",
    )
    gaps, notes = keyword_gaps(chosen_slug, job_data["body"], variants)
    (pack_dir / "KEYWORD_GAPS.md").write_text(
        render_keyword_gaps_md(chosen_slug, gaps, notes),
        encoding="utf-8",
    )

    job_input_path = pack_dir / "job_input.txt"
    job_file = job_data.get("job_file")
    if job_file:
        orig_job_file = Path(job_file)
        if orig_job_file.exists():
            job_input_path.write_text(
                orig_job_file.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

    return {
        "readme": str(pack_dir / "README.txt"),
        "match_json": str(pack_dir / "MATCH.json"),
        "keyword_gaps": str(pack_dir / "KEYWORD_GAPS.md"),
        "job_input": str(job_input_path),
    }
