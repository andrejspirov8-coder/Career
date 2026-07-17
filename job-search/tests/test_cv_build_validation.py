from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.lib.units import mm

CV_DIR = Path(__file__).resolve().parents[1] / "cv"
sys.path.insert(0, str(CV_DIR))

from build_cv_pdf import (  # noqa: E402
    CV_VARIANTS,
    DEFAULT_PHOTO,
    build_pdf,
    parse_cv_markdown,
    validate_cv_markdown,
)


def test_validate_cv_markdown_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        validate_cv_markdown([])


def test_parse_cv_markdown_rejects_missing_name(tmp_path: Path) -> None:
    md = tmp_path / "bad.md"
    md.write_text("## Professional Summary\nHello\n", encoding="utf-8")
    with pytest.raises(ValueError, match="First line"):
        parse_cv_markdown(md)


@pytest.mark.parametrize("slug,md_path,_out_pdf,_paste_path", CV_VARIANTS)
def test_current_cv_variants_build_as_single_page(
    slug: str,
    md_path: Path,
    _out_pdf: Path,
    _paste_path: Path,
    tmp_path: Path,
) -> None:
    visual = tmp_path / f"{slug}.pdf"
    ats = tmp_path / f"{slug}-ats.pdf"

    build_pdf(md_path, visual, layout="canva", photo=DEFAULT_PHOTO)
    build_pdf(md_path, ats, layout="plain")
    expected_target_title = parse_cv_markdown(md_path)[2]

    for pdf in (visual, ats):
        reader = PdfReader(pdf)
        assert len(reader.pages) == 1, f"{pdf.name} unexpectedly spans multiple pages"
        text = reader.pages[0].extract_text() or ""
        assert "ANDREJ SPIROV" in text.upper()
        assert expected_target_title.upper() in text.upper()
        assert "EXPERIENCE" in text.upper() or "PATIRTIS" in text.upper()


def test_long_visual_cv_uses_full_width_continuation_without_photo(
    tmp_path: Path,
) -> None:
    repeated_roles = []
    for index in range(28):
        repeated_roles.extend(
            [
                f"### Operations Role {index} | Company | 2020-2024",
                f"- Led synthetic operations cohort {index} and improved service quality across locations.",
                "- Built clear processes, reporting routines, training plans, and escalation paths.",
                "- Coordinated stakeholders, suppliers, schedules, audits, and customer recovery.",
                "- Measured results, documented risks, and coached managers through corrective actions.",
            ]
        )
    repeated_roles.extend(
        [
            "### CONTINUATION MARKER | Final Company | 2018-2020",
            "- This marker must remain readable on a full-width continuation page.",
        ]
    )
    markdown = tmp_path / "long-cv.md"
    markdown.write_text(
        "\n".join(
            [
                "# Andrej Spirov",
                "andrej@example.com | Vilnius, Lithuania",
                "",
                "## Target Title",
                "Operations Manager",
                "",
                "## Professional Summary",
                "Experienced operations leader focused on people, service, and process improvement.",
                "",
                "## Skills",
                "- Operations management",
                "- Team leadership",
                "",
                "## Languages",
                "- English",
                "",
                "## Experience",
                *repeated_roles,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "long-cv.pdf"

    build_pdf(markdown, output, layout="canva", photo=DEFAULT_PHOTO)

    reader = PdfReader(output)
    assert len(reader.pages) > 1
    extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    for index in range(28):
        assert f"Operations Role {index}" in extracted_text
        assert f"synthetic operations cohort {index}" in extracted_text
    assert "This marker must remain readable" in extracted_text

    continuation_positions: list[float] = []
    marker_seen = False
    for page in reader.pages[1:]:
        resources = page.get("/Resources") or {}
        assert not resources.get("/XObject"), "continuation page repeated the headshot"

        def visit_text(text, _cm, tm, _font_dict, _font_size):
            nonlocal marker_seen
            if "CONTINUATION MARKER" in text:
                marker_seen = True
                continuation_positions.append(float(tm[4]))

        page.extract_text(visitor_text=visit_text)

    assert marker_seen
    assert min(continuation_positions) < 60 * mm
