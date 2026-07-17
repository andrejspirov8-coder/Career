#!/usr/bin/env python3
"""
Build Andrej Spirov's CV PDF from Markdown.

- Layout "canva": grey-blue sidebar, navy accent, two columns, plain skills list.
- Layout "plain": single-column ATS-friendly reading order.

Optional: --photo for circular headshot; system Montserrat/Inter if found, else Helvetica.

Requires: pip install reportlab
"""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    HRFlowable,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from reportlab.platypus.flowables import Flowable

from career_job_search.core.paths import project_path
from career_job_search.cvs.catalogue import cv_variant_tuples
from career_job_search.cvs.markdown import (
    contact_lines as _contact_lines,
)
from career_job_search.cvs.markdown import (
    labels_for_language as _labels_for_language,
)
from career_job_search.cvs.markdown import (
    parse_cv_markdown,
)
from career_job_search.cvs.markdown import (
    validate_cv_markdown as _validate_cv_markdown,
)
from career_job_search.cvs.pdf_styles import (
    NAVY,
    RULE,
    SIDEBAR_BG,
    WHITE,
    register_fonts,
)
from career_job_search.cvs.pdf_styles import (
    compact_visual_styles as _compact_visual_styles,
)
from career_job_search.cvs.pdf_styles import (
    make_styles as _make_styles,
)

validate_cv_markdown = _validate_cv_markdown

HERE = project_path("cv")
JOB_ROOT = project_path()
OUTPUT_DIR = JOB_ROOT / "output"
CANVA_OUTPUT_DIR = OUTPUT_DIR / "canva"
DEFAULT_MD = HERE / "andrej-spirov-cv-luxury-retail.md"
DEFAULT_PHOTO = HERE / "assets" / "andrej-spirov-headshot.png"
# Default exports use the canonical luxury-retail source and filename.
DEFAULT_OUT = OUTPUT_DIR / "andrej-spirov-cv-luxury-retail.pdf"

CV_VARIANTS = cv_variant_tuples(root=JOB_ROOT)


def _sanitize_inline(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .strip()
    )


class ThinRule(Flowable):
    def __init__(self, width: float, thickness: float = 0.6, color=RULE):
        super().__init__()
        self._w = width
        self._t = thickness
        self._c = color
        self._h = 4 * mm

    def wrap(self, availWidth, availHeight):
        self.width = min(self._w, availWidth)
        return self.width, self._h

    def draw(self):
        self.canv.setStrokeColor(self._c)
        self.canv.setLineWidth(self._t)
        self.canv.line(0, self._h / 2, self.width, self._h / 2)


def _format_labeled_line(text: str, font_reg: str, font_bold: str) -> str:
    """Render "Label: detail" with a stronger label while preserving plain source text."""
    label, sep, detail = text.partition(":")
    if not sep or not detail.strip():
        return f"<font name='{font_reg}'>" + _sanitize_inline(text) + "</font>"
    return (
        f"<font name='{font_bold}'>" + _sanitize_inline(label + ":") + "</font> "
        f"<font name='{font_reg}'>" + _sanitize_inline(detail.strip()) + "</font>"
    )


def _draw_circular_photo(
    canvas,
    cx: float,
    cy: float,
    radius: float,
    photo_path: Path,
    initials: str,
    font_bold: str,
) -> None:
    try:
        ir = ImageReader(str(photo_path))
        iw, ih = ir.getSize()
        canvas.saveState()
        p = canvas.beginPath()
        p.circle(cx, cy, radius - 0.3)
        canvas.clipPath(p, stroke=0, fill=0)
        scale = max((2 * radius) / iw, (2 * radius) / ih)
        w, h = iw * scale, ih * scale
        canvas.drawImage(ir, cx - w / 2, cy - h / 2, width=w, height=h, mask="auto")
        canvas.restoreState()
        canvas.setStrokeColor(NAVY)
        canvas.setLineWidth(1)
        canvas.circle(cx, cy, radius, stroke=1, fill=0)
    except Exception:
        canvas.saveState()
        canvas.setStrokeColor(NAVY)
        canvas.setFillColor(WHITE)
        canvas.setLineWidth(1)
        canvas.circle(cx, cy, radius, stroke=1, fill=1)
        canvas.setFillColor(NAVY)
        canvas.setFont(font_bold, 17)
        canvas.drawCentredString(cx, cy - 5 * mm, initials)
        canvas.restoreState()


def _build_canva_bytes(
    *,
    name: str,
    contact: str,
    target_title: str,
    summary: str,
    selected_achievements: list[str],
    recent_focus: str,
    skills: list[str],
    languages: list[str],
    roles: list[tuple[str, list[str]]],
    labels: dict[str, str],
    styles: dict[str, ParagraphStyle],
    font_reg: str,
    font_bold: str,
    photo: Path | None,
) -> tuple[bytes, int]:
    """Build the visual CV in memory and return its bytes and page count."""

    pw, ph = A4
    lm, rm, tm, bm = 0, 12 * mm, 11 * mm, 11 * mm
    inner_left = 12 * mm
    usable_w = pw - inner_left - rm
    left_w = usable_w * 0.33
    gap = 4 * mm
    right_w = usable_w - left_w - gap
    frame_h = ph - tm - bm

    left_frame = Frame(
        inner_left,
        bm,
        left_w,
        frame_h,
        leftPadding=8,
        rightPadding=8,
        topPadding=4,
        bottomPadding=6,
        id="left",
    )
    right_frame = Frame(
        inner_left + left_w + gap,
        bm,
        right_w,
        frame_h,
        leftPadding=0,
        rightPadding=0,
        topPadding=2,
        bottomPadding=6,
        id="right",
    )
    continuation_frame = Frame(
        inner_left,
        bm,
        usable_w,
        frame_h,
        leftPadding=0,
        rightPadding=0,
        topPadding=2,
        bottomPadding=6,
        id="continuation",
    )

    initials = "".join(part[0] for part in name.split()[:2]).upper() or "AS"
    sidebar_x2 = inner_left + left_w + 0.5 * mm
    r_photo = 15.5 * mm

    def on_first_page(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(SIDEBAR_BG)
        canvas.rect(0, 0, sidebar_x2, ph, stroke=0, fill=1)
        cx = inner_left + left_w / 2
        cy = bm + frame_h - 22 * mm

        if photo and photo.exists():
            _draw_circular_photo(canvas, cx, cy, r_photo, photo, initials, font_bold)
        else:
            canvas.setStrokeColor(NAVY)
            canvas.setFillColor(WHITE)
            canvas.setLineWidth(1)
            canvas.circle(cx, cy, r_photo, stroke=1, fill=1)
            canvas.setFillColor(NAVY)
            canvas.setFont(font_bold, 17)
            canvas.drawCentredString(cx, cy - 5 * mm, initials)
        canvas.restoreState()

    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=lm,
        rightMargin=rm,
        topMargin=tm,
        bottomMargin=bm,
        title=name,
        author=name,
        subject="CV",
    )
    doc.addPageTemplates(
        [
            PageTemplate(
                id="two_col",
                frames=[left_frame, right_frame],
                onPage=on_first_page,
                autoNextPageTemplate="continuation",
            ),
            PageTemplate(id="continuation", frames=[continuation_frame]),
        ]
    )

    left_story: list = []
    left_story.append(Spacer(1, 34 * mm))
    left_story.append(Paragraph(labels["contact"], styles["L_Section"]))
    for line in _contact_lines(contact):
        left_story.append(Paragraph(_sanitize_inline(line), styles["L_Body"]))

    left_story.append(Spacer(1, 5 * mm))
    left_story.append(Paragraph(labels["skills"], styles["L_Section"]))
    for skill in skills:
        left_story.append(
            Paragraph(
                _format_labeled_line(skill, font_reg, font_bold), styles["L_Skill"]
            )
        )

    if languages:
        left_story.append(Spacer(1, 3 * mm))
        left_story.append(Paragraph(labels["languages"], styles["L_Section"]))
        for lang in languages:
            left_story.append(Paragraph(_sanitize_inline(lang), styles["L_Body"]))

    right_story: list = []
    display_name = name.upper()
    right_story.append(Paragraph(_sanitize_inline(display_name), styles["R_Name"]))
    right_story.append(
        Paragraph(_sanitize_inline(target_title.upper()), styles["R_Sub"])
    )
    right_story.append(ThinRule(right_w))
    right_story.append(Paragraph(labels["profile"], styles["R_Section"]))
    right_story.append(
        Paragraph(
            f"<font name='{font_reg}'>" + _sanitize_inline(summary) + "</font>",
            styles["R_Body"],
        )
    )
    if selected_achievements:
        right_story.append(
            Paragraph(labels["selected_achievements"], styles["R_Section"])
        )
        for achievement in selected_achievements:
            right_story.append(
                Paragraph(
                    f"<font name='{font_reg}'>"
                    + _sanitize_inline(f"- {achievement}")
                    + "</font>",
                    styles["R_Bullet"],
                )
            )
    if recent_focus:
        right_story.append(Paragraph(labels["recent_focus"], styles["R_Section"]))
        right_story.append(
            Paragraph(
                f"<font name='{font_reg}'>"
                + _sanitize_inline(recent_focus)
                + "</font>",
                styles["R_Body"],
            )
        )
    right_story.append(Paragraph(labels["experience"], styles["R_Section"]))

    for heading, bullets in roles:
        right_story.append(
            Paragraph(
                f"<font name='{font_bold}'>" + _sanitize_inline(heading) + "</font>",
                styles["R_Role"],
            )
        )
        for b in bullets:
            right_story.append(
                Paragraph(
                    f"<font name='{font_reg}'>"
                    + _sanitize_inline(f"- {b}")
                    + "</font>",
                    styles["R_Bullet"],
                )
            )

    story = left_story + [FrameBreak()] + right_story
    doc.build(story)
    return buffer.getvalue(), doc.page


def build_pdf(
    md_path: Path,
    out_pdf: Path,
    *,
    layout: str = "canva",
    photo: Path | None = None,
) -> None:
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    font_reg, font_bold = register_fonts()
    styles = _make_styles(font_reg, font_bold)

    (
        name,
        contact,
        target_title,
        document_language,
        summary,
        selected_achievements,
        recent_focus,
        skills,
        languages,
        roles,
    ) = parse_cv_markdown(md_path)
    labels = _labels_for_language(document_language)

    if layout == "plain":
        _build_plain(
            name,
            contact,
            target_title,
            summary,
            selected_achievements,
            recent_focus,
            skills,
            languages,
            roles,
            labels,
            styles,
            font_reg,
            font_bold,
            out_pdf,
        )
        return

    build_args = {
        "name": name,
        "contact": contact,
        "target_title": target_title,
        "summary": summary,
        "selected_achievements": selected_achievements,
        "recent_focus": recent_focus,
        "skills": skills,
        "languages": languages,
        "roles": roles,
        "labels": labels,
        "font_reg": font_reg,
        "font_bold": font_bold,
        "photo": photo,
    }
    pdf_bytes, page_count = _build_canva_bytes(styles=styles, **build_args)
    if page_count > 1:
        compact_bytes, compact_page_count = _build_canva_bytes(
            styles=_compact_visual_styles(styles),
            **build_args,
        )
        if compact_page_count < page_count:
            pdf_bytes = compact_bytes

    out_pdf.write_bytes(pdf_bytes)


def _build_plain(
    name: str,
    contact: str,
    target_title: str,
    summary: str,
    selected_achievements: list[str],
    recent_focus: str,
    skills: list[str],
    languages: list[str],
    roles: list[tuple[str, list[str]]],
    labels: dict[str, str],
    styles: dict[str, ParagraphStyle],
    font_reg: str,
    font_bold: str,
    out_pdf: Path,
) -> None:
    """ATS-oriented single column: Contact, Summary, Skills, Languages, Experience."""
    pw, ph = A4
    margin = 14 * mm
    doc = SimpleDocTemplate(
        str(out_pdf),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=9 * mm,
        bottomMargin=9 * mm,
        title=name,
        author=name,
        subject="CV",
    )
    story: list = []
    story.append(Paragraph(_sanitize_inline(name), styles["P_Name"]))
    story.append(Paragraph(_sanitize_inline(target_title.upper()), styles["R_Sub"]))
    story.append(
        HRFlowable(width="100%", thickness=0.5, spaceBefore=2, spaceAfter=6, color=RULE)
    )
    story.append(Paragraph(labels["contact"], styles["P_Heading"]))
    for line in _contact_lines(contact):
        story.append(Paragraph(_sanitize_inline(line), styles["P_Contact"]))

    story.append(Paragraph(labels["summary"], styles["P_Heading"]))
    story.append(
        Paragraph(
            f"<font name='{font_reg}'>" + _sanitize_inline(summary) + "</font>",
            styles["P_Body"],
        )
    )

    if selected_achievements:
        story.append(Paragraph(labels["selected_achievements"], styles["P_Heading"]))
        for achievement in selected_achievements:
            story.append(
                Paragraph(
                    f"<font name='{font_reg}'>"
                    + _sanitize_inline(f"- {achievement}")
                    + "</font>",
                    styles["P_ListLine"],
                )
            )

    if recent_focus:
        story.append(Paragraph(labels["recent_focus"], styles["P_Heading"]))
        story.append(
            Paragraph(
                f"<font name='{font_reg}'>"
                + _sanitize_inline(recent_focus)
                + "</font>",
                styles["P_Body"],
            )
        )

    if skills:
        story.append(Paragraph(labels["key_skills"], styles["P_Heading"]))
        for t in skills:
            story.append(
                Paragraph(
                    f"<font name='{font_reg}'>"
                    + _sanitize_inline(f"- {t}")
                    + "</font>",
                    styles["P_ListLine"],
                )
            )

    if languages:
        story.append(Paragraph(labels["languages"], styles["P_Heading"]))
        for lang in languages:
            story.append(
                Paragraph(
                    f"<font name='{font_reg}'>"
                    + _sanitize_inline(f"- {lang}")
                    + "</font>",
                    styles["P_ListLine"],
                )
            )

    story.append(Paragraph(labels["experience"], styles["P_Heading"]))
    for heading, bullets in roles:
        story.append(
            Paragraph(
                f"<font name='{font_bold}'>" + _sanitize_inline(heading) + "</font>",
                styles["P_ExpRole"],
            )
        )
        for b in bullets:
            story.append(
                Paragraph(
                    f"<font name='{font_reg}'>"
                    + _sanitize_inline(f"- {b}")
                    + "</font>",
                    styles["P_ExpBullet"],
                )
            )

    doc.build(story)


def build_canva_paste(
    md_path: Path, out_txt: Path, *, design_hint: str | None = None
) -> None:
    (
        name,
        contact,
        target_title,
        document_language,
        summary,
        selected_achievements,
        recent_focus,
        skills,
        languages,
        roles,
    ) = parse_cv_markdown(md_path)
    labels = _labels_for_language(document_language)
    out_txt.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    if design_hint:
        lines.append(f"# Paste into Canva resume {design_hint}")
    else:
        lines.append("# Paste into Canva resume")
    lines.append(f"# Generated from {md_path.name}")
    lines.append(
        "# Remove any fake template education, address, websites, social links, or placeholder phone numbers."
    )
    lines.append("")
    lines.append(name)
    lines.append(target_title)
    lines.append(contact)
    lines.append("")
    lines.append(labels["summary"])
    lines.append(summary)
    if selected_achievements:
        lines.append("")
        lines.append(labels["selected_achievements"])
        lines.extend(selected_achievements)
    if recent_focus:
        lines.append("")
        lines.append(labels["recent_focus"])
        lines.append(recent_focus)
    lines.append("")
    lines.append(labels["key_skills"])
    lines.extend(skills)
    lines.append("")
    lines.append(labels["experience"])
    for heading, bullets in roles:
        lines.append("")
        lines.append(heading)
        lines.extend(bullets)
    lines.append("")
    lines.append(labels["languages"])
    lines.extend(languages)
    out_txt.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_all() -> None:
    default_photo = DEFAULT_PHOTO if DEFAULT_PHOTO.exists() else None
    for _slug, md_path, out_pdf, paste_path in CV_VARIANTS:
        build_pdf(md_path, out_pdf, layout="canva", photo=default_photo)
        build_pdf(md_path, out_pdf.with_name(f"{out_pdf.stem}-ats.pdf"), layout="plain")
        build_canva_paste(md_path, paste_path)


def build_variant(slug: str) -> tuple[Path, Path, Path]:
    selected = next((row for row in CV_VARIANTS if row[0] == slug), None)
    if selected is None:
        raise ValueError(f"Unknown CV variant: {slug}")
    _slug, md_path, out_pdf, paste_path = selected
    default_photo = DEFAULT_PHOTO if DEFAULT_PHOTO.exists() else None
    ats_pdf = out_pdf.with_name(f"{out_pdf.stem}-ats.pdf")
    build_pdf(md_path, out_pdf, layout="canva", photo=default_photo)
    build_pdf(md_path, ats_pdf, layout="plain")
    build_canva_paste(md_path, paste_path)
    return out_pdf, ats_pdf, paste_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build CV PDF from Markdown (Canva-style two-column or plain ATS)."
    )
    parser.add_argument(
        "--md", type=Path, default=DEFAULT_MD, help="Path to source Markdown."
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="Output PDF path."
    )
    build_group = parser.add_mutually_exclusive_group()
    build_group.add_argument(
        "--all",
        action="store_true",
        help="Build all CV variants, ATS PDFs, and generated Canva paste files.",
    )
    build_group.add_argument(
        "--variant",
        choices=tuple(row[0] for row in CV_VARIANTS),
        help="Build one named CV variant in visual, ATS, and Canva-paste formats.",
    )
    parser.add_argument(
        "--write-canva-paste",
        action="store_true",
        help="Also write a Canva paste text file for the selected Markdown CV.",
    )
    parser.add_argument(
        "--paste-out",
        type=Path,
        default=None,
        help="Output path for --write-canva-paste. Defaults to output/canva/andrej-spirov-cv-luxury-retail-canva.txt.",
    )
    parser.add_argument(
        "--layout",
        choices=("canva", "plain"),
        default="canva",
        help="canva: two-column visual; plain: single-column ATS-friendly order.",
    )
    parser.add_argument(
        "--photo",
        type=Path,
        default=None,
        help="Optional square-ish image (PNG/JPG) for circular headshot in canva layout.",
    )
    args = parser.parse_args()
    if args.all:
        build_all()
        print(
            f"Wrote all CV variants under {OUTPUT_DIR} and Canva paste files under {CANVA_OUTPUT_DIR}"
        )
        return
    if args.variant:
        visual_pdf, ats_pdf, paste_path = build_variant(args.variant)
        print(
            "Wrote selected CV variant: "
            f"{visual_pdf.resolve()}, {ats_pdf.resolve()}, and {paste_path.resolve()}"
        )
        return
    if not args.md.exists():
        raise SystemExit(f"Missing Markdown file: {args.md}")
    if args.photo and not args.photo.exists():
        raise SystemExit(f"Photo not found: {args.photo}")
    build_pdf(args.md, args.out, layout=args.layout, photo=args.photo)
    if args.write_canva_paste:
        paste_out = args.paste_out or (
            CANVA_OUTPUT_DIR / "andrej-spirov-cv-luxury-retail-canva.txt"
        )
        build_canva_paste(args.md, paste_out)
        print(f"Wrote {paste_out.resolve()} (Canva paste)")
    print(f"Wrote {args.out.resolve()} (layout={args.layout})")


if __name__ == "__main__":
    main()
