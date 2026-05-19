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
from pathlib import Path

from reportlab.lib.colors import HexColor, black
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
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

HERE = Path(__file__).resolve().parent
JOB_ROOT = HERE.parent
OUTPUT_DIR = JOB_ROOT / "output"
CANVA_OUTPUT_DIR = OUTPUT_DIR / "canva"
DEFAULT_MD = HERE / "andrej-spirov-cv-luxury-retail.md"
DEFAULT_PHOTO = HERE / "assets" / "andrej-spirov-headshot.png"
# Default exports use the canonical luxury-retail source and filename.
DEFAULT_OUT = OUTPUT_DIR / "andrej-spirov-cv-luxury-retail.pdf"

CV_VARIANTS = (
    ("luxury-retail", HERE / "andrej-spirov-cv-luxury-retail.md", OUTPUT_DIR / "andrej-spirov-cv-luxury-retail.pdf", CANVA_OUTPUT_DIR / "andrej-spirov-cv-luxury-retail-canva.txt"),
    ("luxury-retail-lt", HERE / "andrej-spirov-cv-luxury-retail-lt.md", OUTPUT_DIR / "andrej-spirov-cv-luxury-retail-lt.pdf", CANVA_OUTPUT_DIR / "andrej-spirov-cv-luxury-retail-lt-canva.txt"),
    ("operations-management", HERE / "andrej-spirov-cv-operations-management.md", OUTPUT_DIR / "andrej-spirov-cv-operations-management.pdf", CANVA_OUTPUT_DIR / "andrej-spirov-cv-operations-management-canva.txt"),
    ("it-business", HERE / "andrej-spirov-cv-it-business.md", OUTPUT_DIR / "andrej-spirov-cv-it-business.pdf", CANVA_OUTPUT_DIR / "andrej-spirov-cv-it-business-canva.txt"),
)

NAVY = HexColor("#2E3152")
SIDEBAR_BG = HexColor("#DDE3EB")
BODY = HexColor("#333333")
MUTED = HexColor("#6B6F76")
RULE = HexColor("#C8CED6")
WHITE = HexColor("#FFFFFF")
LIGHT_DOT = HexColor("#B8C0CC")

# Module-level font names for canvas drawing (set by register_fonts)
_FONT_BOLD_CANVAS = "Helvetica-Bold"
_FONT_REG_CANVAS = "Helvetica"


def _sanitize_inline(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .strip()
    )


def parse_cv_markdown(
    md_path: Path,
) -> tuple[str, str, str, str, str, str, list[str], list[str], list[tuple[str, list[str]]]]:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    i = 0

    assert lines[i].startswith("# "), "First line must be # Name"
    name = lines[i][2:].strip()
    i += 1

    while i < len(lines) and not lines[i].strip():
        i += 1

    contact_chunks: list[str] = []
    while i < len(lines) and not lines[i].startswith("## "):
        s = lines[i].strip()
        if s and s != "---":
            contact_chunks.append(s)
        i += 1
    contact = " ".join(contact_chunks)

    summary = ""
    target_title = "LUXURY RETAIL LEADER"
    document_language = "en"
    recent_focus = ""
    experience: list[tuple[str, list[str]]] = []
    skills: list[str] = []
    languages: list[str] = []

    while i < len(lines):
        line = lines[i]
        if not line.startswith("## "):
            i += 1
            continue
        title = line[3:].strip()
        i += 1
        body_lines: list[str] = []
        while i < len(lines) and not lines[i].startswith("## "):
            body_lines.append(lines[i])
            i += 1

        body_trim = []
        for bl in body_lines:
            ts = bl.strip()
            if not ts or ts == "---":
                continue
            body_trim.append(bl)

        if title == "Document Language":
            document_language = (" ".join([x.strip() for x in body_trim if x.strip()]) or "en").lower()
        elif title == "Target Title":
            target_title = " ".join([x.strip() for x in body_trim if x.strip()]) or target_title
        elif title == "Professional Summary":
            summary = " ".join([x.strip() for x in body_trim if x.strip()])
        elif title == "Recent Focus":
            recent_focus = " ".join([x.strip() for x in body_trim if x.strip()])
        elif title == "Experience":
            exp_lines = "\n".join(body_trim).splitlines()
            j = 0
            while j < len(exp_lines):
                stripped = exp_lines[j].strip()
                if stripped.startswith("###"):
                    heading = stripped.lstrip("#").strip()
                    bullets = []
                    j += 1
                    while j < len(exp_lines) and not exp_lines[j].strip():
                        j += 1
                    while j < len(exp_lines) and exp_lines[j].strip().startswith("- "):
                        bullets.append(exp_lines[j].strip()[2:].strip())
                        j += 1
                    experience.append((heading, bullets))
                else:
                    j += 1
        elif title in {"Technical Skills", "Core Skills", "Skills"}:
            for bl in body_trim:
                t = bl.strip()
                if t.startswith("- "):
                    skills.append(t[2:].strip())
        elif title == "Languages":
            for bl in body_trim:
                t = bl.strip()
                if t.startswith("- "):
                    languages.append(t[2:].strip())

    return name, contact, target_title, document_language, summary, recent_focus, skills, languages, experience


def _labels_for_language(document_language: str) -> dict[str, str]:
    if document_language.startswith("lt"):
        return {
            "contact": "KONTAKTAI",
            "skills": "ĮGŪDŽIAI",
            "languages": "KALBOS",
            "profile": "PROFILIS",
            "recent_focus": "DABARTINIS TIKSLAS",
            "experience": "PATIRTIS",
            "summary": "PROFESINĖ SANTRAUKA",
            "key_skills": "PAGRINDINIAI ĮGŪDŽIAI",
        }
    return {
        "contact": "CONTACT",
        "skills": "SKILLS",
        "languages": "LANGUAGES",
        "profile": "PROFILE",
        "recent_focus": "RECENT FOCUS",
        "experience": "EXPERIENCE",
        "summary": "PROFESSIONAL SUMMARY",
        "key_skills": "KEY SKILLS",
    }


def _contact_lines(contact: str) -> list[str]:
    parts = [p.strip() for p in contact.split("|") if p.strip()]
    return parts if parts else [contact]


def _discover_ttf_pair() -> tuple[Path | None, Path | None]:
    """Find Montserrat or Inter regular + bold TTF for embedding."""
    names = (
        ("Montserrat-Regular.ttf", "Montserrat-Bold.ttf"),
        ("MontserratRegular.ttf", "MontserratBold.ttf"),
        ("Inter-Regular.ttf", "Inter-Bold.ttf"),
        ("InterRegular.ttf", "InterBold.ttf"),
        ("Arial.ttf", "Arial Bold.ttf"),
        ("Arial Unicode.ttf", "Arial Unicode.ttf"),
    )
    roots = [
        HERE / "fonts",
        Path("/Library/Fonts"),
        Path.home() / "Library/Fonts",
        Path("/System/Library/Fonts/Supplemental"),
    ]
    for reg_name, bold_name in names:
        reg_path = bold_path = None
        for root in roots:
            if not root.is_dir():
                continue
            for p in root.rglob(reg_name):
                reg_path = p
                break
            for p in root.rglob(bold_name):
                bold_path = p
                break
            if reg_path and bold_path:
                return reg_path, bold_path
        for root in roots:
            if not root.is_dir():
                continue
            for p in root.rglob(reg_name):
                reg_path = p
                break
            for p in root.rglob(bold_name):
                bold_path = p
                break
        if reg_path or bold_path:
            return reg_path or bold_path, bold_path or reg_path

    loose_roots = [*roots, Path("/System/Library/Fonts")]
    for prefix in ("Montserrat", "Inter"):
        cands = []
        for root in loose_roots:
            if not root.is_dir():
                continue
            for p in root.rglob(f"{prefix}*.ttf"):
                if "variable" in p.name.lower() or "italic" in p.name.lower():
                    continue
                cands.append(p)
        regular = next((p for p in cands if "bold" not in p.name.lower()), None)
        bold = next((p for p in cands if "bold" in p.name.lower() and "semi" not in p.name.lower()), None)
        if regular and bold:
            return regular, bold
        if cands:
            return cands[0], cands[0]
    return None, None


def register_fonts() -> tuple[str, str]:
    """Register optional Montserrat/Inter; return (regular_name, bold_name) for Paragraph."""
    global _FONT_REG_CANVAS, _FONT_BOLD_CANVAS
    reg_path, bold_path = _discover_ttf_pair()
    rname, bname = "CVSans", "CVSansBd"

    try:
        registered = set(pdfmetrics.getRegisteredFontNames())
        if reg_path and reg_path.exists():
            if rname not in registered:
                pdfmetrics.registerFont(TTFont(rname, str(reg_path)))
        if bold_path and bold_path.exists() and bold_path.resolve() != (reg_path.resolve() if reg_path else None):
            if bname not in set(pdfmetrics.getRegisteredFontNames()):
                pdfmetrics.registerFont(TTFont(bname, str(bold_path)))
        elif reg_path and reg_path.exists():
            bname = rname

        registered = set(pdfmetrics.getRegisteredFontNames())
        if rname in registered:
            _FONT_REG_CANVAS = rname
            _FONT_BOLD_CANVAS = bname if bname in registered else rname
            return rname, _FONT_BOLD_CANVAS
    except Exception:
        pass

    _FONT_REG_CANVAS = "Helvetica"
    _FONT_BOLD_CANVAS = "Helvetica-Bold"
    return "Helvetica", "Helvetica-Bold"


def _make_styles(font_reg: str, font_bold: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    s: dict[str, ParagraphStyle] = {}

    # Canva-style scale: name ~20-24pt, headings ~11-12pt, body ~10pt, line height ~1.15-1.25
    s["L_Section"] = ParagraphStyle(
        "L_Section",
        parent=base["Normal"],
        fontName=font_bold,
        fontSize=9,
        leading=11,
        textColor=NAVY,
        spaceBefore=0,
        spaceAfter=5,
        alignment=TA_LEFT,
    )
    s["L_Body"] = ParagraphStyle(
        "L_Body",
        parent=base["Normal"],
        fontName=font_reg,
        fontSize=8.6,
        leading=10.3,
        textColor=BODY,
        spaceAfter=3,
        alignment=TA_LEFT,
    )
    s["L_Skill"] = ParagraphStyle(
        "L_Skill",
        parent=base["Normal"],
        fontName=font_reg,
        fontSize=8.4,
        leading=10.1,
        textColor=BODY,
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    s["R_Name"] = ParagraphStyle(
        "R_Name",
        parent=base["Normal"],
        fontName=font_bold,
        fontSize=22,
        leading=24,
        textColor=NAVY,
        spaceAfter=2,
        alignment=TA_LEFT,
    )
    s["R_Sub"] = ParagraphStyle(
        "R_Sub",
        parent=base["Normal"],
        fontName=font_reg,
        fontSize=9.5,
        leading=11.4,
        textColor=MUTED,
        spaceAfter=5,
        alignment=TA_LEFT,
    )
    s["R_Section"] = ParagraphStyle(
        "R_Section",
        parent=base["Normal"],
        fontName=font_bold,
        fontSize=11,
        leading=13,
        textColor=NAVY,
        spaceBefore=8,
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    s["R_Body"] = ParagraphStyle(
        "R_Body",
        parent=base["Normal"],
        fontName=font_reg,
        fontSize=9.3,
        leading=11.2,
        textColor=BODY,
        spaceAfter=6,
        alignment=TA_LEFT,
    )
    s["R_Role"] = ParagraphStyle(
        "R_Role",
        parent=base["Normal"],
        fontName=font_bold,
        fontSize=9,
        leading=10.5,
        textColor=NAVY,
        spaceBefore=5,
        spaceAfter=2,
        alignment=TA_LEFT,
    )
    s["R_Bullet"] = ParagraphStyle(
        "R_Bullet",
        parent=base["Normal"],
        fontName=font_reg,
        fontSize=9.1,
        leading=10.7,
        textColor=BODY,
        leftIndent=10,
        firstLineIndent=-10,
        spaceAfter=2,
        alignment=TA_LEFT,
    )

    s["P_Heading"] = ParagraphStyle(
        "P_Heading",
        parent=base["Normal"],
        fontName=font_bold,
        fontSize=10,
        leading=11.3,
        textColor=NAVY,
        spaceBefore=5,
        spaceAfter=3,
        alignment=TA_LEFT,
    )
    s["P_Body"] = ParagraphStyle(
        "P_Body",
        parent=base["Normal"],
        fontName=font_reg,
        fontSize=8.7,
        leading=10.4,
        textColor=BODY,
        spaceAfter=3,
        alignment=TA_LEFT,
    )
    s["P_Contact"] = ParagraphStyle(
        "P_Contact",
        parent=base["Normal"],
        fontName=font_reg,
        fontSize=9,
        leading=11,
        textColor=BODY,
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    s["P_ExpRole"] = ParagraphStyle(
        "P_ExpRole",
        parent=base["Normal"],
        fontName=font_bold,
        fontSize=9.1,
        leading=10.4,
        textColor=NAVY,
        spaceBefore=4,
        spaceAfter=2,
        alignment=TA_LEFT,
    )
    s["P_ListLine"] = ParagraphStyle(
        "P_ListLine",
        parent=base["Normal"],
        fontName=font_reg,
        fontSize=8.7,
        leading=10.3,
        textColor=BODY,
        spaceAfter=1,
        alignment=TA_LEFT,
    )
    s["P_ExpBullet"] = ParagraphStyle(
        "P_ExpBullet",
        parent=base["Normal"],
        fontName=font_reg,
        fontSize=8.7,
        leading=10.3,
        textColor=BODY,
        leftIndent=10,
        firstLineIndent=-10,
        spaceAfter=1,
        alignment=TA_LEFT,
    )
    s["P_Name"] = ParagraphStyle(
        "P_Name",
        parent=base["Normal"],
        fontName=font_bold,
        fontSize=17,
        leading=20,
        textColor=NAVY,
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    return s


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


def _draw_circular_photo(canvas, cx: float, cy: float, radius: float, photo_path: Path, initials: str) -> None:
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
        canvas.setFont(_FONT_BOLD_CANVAS, 17)
        canvas.drawCentredString(cx, cy - 5 * mm, initials)
        canvas.restoreState()


def build_pdf(
    md_path: Path,
    out_pdf: Path,
    *,
    layout: str = "canva",
    photo: Path | None = None,
) -> None:
    global _FONT_BOLD_CANVAS, _FONT_REG_CANVAS
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    font_reg, font_bold = register_fonts()
    _FONT_REG_CANVAS, _FONT_BOLD_CANVAS = font_reg, font_bold
    styles = _make_styles(font_reg, font_bold)

    name, contact, target_title, document_language, summary, recent_focus, skills, languages, roles = parse_cv_markdown(md_path)
    labels = _labels_for_language(document_language)

    if layout == "plain":
        _build_plain(name, contact, target_title, summary, recent_focus, skills, languages, roles, labels, styles, font_reg, font_bold, out_pdf)
        return

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

    initials = "".join(part[0] for part in name.split()[:2]).upper() or "AS"
    sidebar_x2 = inner_left + left_w + 0.5 * mm
    r_photo = 15.5 * mm

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(SIDEBAR_BG)
        canvas.rect(0, 0, sidebar_x2, ph, stroke=0, fill=1)
        cx = inner_left + left_w / 2
        cy = bm + frame_h - 22 * mm

        if photo and photo.exists():
            _draw_circular_photo(canvas, cx, cy, r_photo, photo, initials)
        else:
            canvas.setStrokeColor(NAVY)
            canvas.setFillColor(WHITE)
            canvas.setLineWidth(1)
            canvas.circle(cx, cy, r_photo, stroke=1, fill=1)
            canvas.setFillColor(NAVY)
            canvas.setFont(_FONT_BOLD_CANVAS, 17)
            canvas.drawCentredString(cx, cy - 5 * mm, initials)
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(out_pdf),
        pagesize=A4,
        leftMargin=lm,
        rightMargin=rm,
        topMargin=tm,
        bottomMargin=bm,
        title=name,
        author=name,
        subject="CV",
    )
    doc.addPageTemplates([PageTemplate(id="two_col", frames=[left_frame, right_frame], onPage=on_page)])

    left_story: list = []
    left_story.append(Spacer(1, 34 * mm))
    left_story.append(Paragraph(labels["contact"], styles["L_Section"]))
    for line in _contact_lines(contact):
        left_story.append(Paragraph(_sanitize_inline(line), styles["L_Body"]))

    left_story.append(Spacer(1, 5 * mm))
    left_story.append(Paragraph(labels["skills"], styles["L_Section"]))
    for skill in skills:
        left_story.append(Paragraph(_format_labeled_line(skill, font_reg, font_bold), styles["L_Skill"]))

    if languages:
        left_story.append(Spacer(1, 3 * mm))
        left_story.append(Paragraph(labels["languages"], styles["L_Section"]))
        for lang in languages:
            left_story.append(Paragraph(_sanitize_inline(lang), styles["L_Body"]))

    right_story: list = []
    display_name = name.upper()
    right_story.append(Paragraph(_sanitize_inline(display_name), styles["R_Name"]))
    right_story.append(Paragraph(_sanitize_inline(target_title.upper()), styles["R_Sub"]))
    right_story.append(ThinRule(right_w))
    right_story.append(Paragraph(labels["profile"], styles["R_Section"]))
    right_story.append(
        Paragraph(f"<font name='{font_reg}'>" + _sanitize_inline(summary) + "</font>", styles["R_Body"])
    )
    if recent_focus:
        right_story.append(Paragraph(labels["recent_focus"], styles["R_Section"]))
        right_story.append(
            Paragraph(f"<font name='{font_reg}'>" + _sanitize_inline(recent_focus) + "</font>", styles["R_Body"])
        )
    right_story.append(Paragraph(labels["experience"], styles["R_Section"]))

    for heading, bullets in roles:
        right_story.append(
            Paragraph(f"<font name='{font_bold}'>" + _sanitize_inline(heading) + f"</font>", styles["R_Role"])
        )
        for b in bullets:
            right_story.append(
                Paragraph(f"<font name='{font_reg}'>" + _sanitize_inline(f"- {b}") + "</font>", styles["R_Bullet"])
            )

    story = left_story + [FrameBreak()] + right_story
    doc.build(story)


def _build_plain(
    name: str,
    contact: str,
    target_title: str,
    summary: str,
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
    story.append(HRFlowable(width="100%", thickness=0.5, spaceBefore=2, spaceAfter=6, color=RULE))
    story.append(Paragraph(labels["contact"], styles["P_Heading"]))
    for line in _contact_lines(contact):
        story.append(Paragraph(_sanitize_inline(line), styles["P_Contact"]))

    story.append(Paragraph(labels["summary"], styles["P_Heading"]))
    story.append(Paragraph(f"<font name='{font_reg}'>" + _sanitize_inline(summary) + "</font>", styles["P_Body"]))

    if recent_focus:
        story.append(Paragraph(labels["recent_focus"], styles["P_Heading"]))
        story.append(Paragraph(f"<font name='{font_reg}'>" + _sanitize_inline(recent_focus) + "</font>", styles["P_Body"]))

    if skills:
        story.append(Paragraph(labels["key_skills"], styles["P_Heading"]))
        for t in skills:
            story.append(Paragraph(f"<font name='{font_reg}'>" + _sanitize_inline(f"- {t}") + "</font>", styles["P_ListLine"]))

    if languages:
        story.append(Paragraph(labels["languages"], styles["P_Heading"]))
        for lang in languages:
            story.append(Paragraph(f"<font name='{font_reg}'>" + _sanitize_inline(f"- {lang}") + "</font>", styles["P_ListLine"]))

    story.append(Paragraph(labels["experience"], styles["P_Heading"]))
    for heading, bullets in roles:
        story.append(
            Paragraph(f"<font name='{font_bold}'>" + _sanitize_inline(heading) + f"</font>", styles["P_ExpRole"])
        )
        for b in bullets:
            story.append(
                Paragraph(f"<font name='{font_reg}'>" + _sanitize_inline(f"- {b}") + "</font>", styles["P_ExpBullet"])
            )

    doc.build(story)


def build_canva_paste(md_path: Path, out_txt: Path, *, design_hint: str | None = None) -> None:
    name, contact, target_title, document_language, summary, recent_focus, skills, languages, roles = parse_cv_markdown(md_path)
    labels = _labels_for_language(document_language)
    out_txt.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    if design_hint:
        lines.append(f"# Paste into Canva resume {design_hint}")
    else:
        lines.append("# Paste into Canva resume")
    lines.append(f"# Generated from {md_path.name}")
    lines.append("# Remove any fake template education, address, websites, social links, or placeholder phone numbers.")
    lines.append("")
    lines.append(name)
    lines.append(target_title)
    lines.append(contact)
    lines.append("")
    lines.append(labels["summary"])
    lines.append(summary)
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Build CV PDF from Markdown (Canva-style two-column or plain ATS).")
    parser.add_argument("--md", type=Path, default=DEFAULT_MD, help="Path to source Markdown.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output PDF path.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Build all CV variants, ATS PDFs, and generated Canva paste files.",
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
        print(f"Wrote all CV variants under {OUTPUT_DIR} and Canva paste files under {CANVA_OUTPUT_DIR}")
        return
    if not args.md.exists():
        raise SystemExit(f"Missing Markdown file: {args.md}")
    if args.photo and not args.photo.exists():
        raise SystemExit(f"Photo not found: {args.photo}")
    build_pdf(args.md, args.out, layout=args.layout, photo=args.photo)
    if args.write_canva_paste:
        paste_out = args.paste_out or (CANVA_OUTPUT_DIR / "andrej-spirov-cv-luxury-retail-canva.txt")
        build_canva_paste(args.md, paste_out)
        print(f"Wrote {paste_out.resolve()} (Canva paste)")
    print(f"Wrote {args.out.resolve()} (layout={args.layout})")


if __name__ == "__main__":
    main()
