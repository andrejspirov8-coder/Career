"""Fonts, colours, and paragraph styles for CV PDF rendering."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from career_job_search.core.paths import project_path

NAVY = HexColor("#2E3152")
SIDEBAR_BG = HexColor("#DDE3EB")
BODY = HexColor("#333333")
MUTED = HexColor("#6B6F76")
RULE = HexColor("#C8CED6")
WHITE = HexColor("#FFFFFF")


def _discover_ttf_pair() -> tuple[Path | None, Path | None]:
    """Find a regular and bold font pair suitable for PDF embedding."""

    names = (
        ("Montserrat-Regular.ttf", "Montserrat-Bold.ttf"),
        ("MontserratRegular.ttf", "MontserratBold.ttf"),
        ("Inter-Regular.ttf", "Inter-Bold.ttf"),
        ("InterRegular.ttf", "InterBold.ttf"),
        ("Arial.ttf", "Arial Bold.ttf"),
        ("Arial Unicode.ttf", "Arial Unicode.ttf"),
    )
    roots = [
        project_path("cv", "fonts"),
        Path("/Library/Fonts"),
        Path.home() / "Library/Fonts",
        Path("/System/Library/Fonts/Supplemental"),
    ]
    for regular_name, bold_name in names:
        regular_path = bold_path = None
        for root in roots:
            if not root.is_dir():
                continue
            regular_path = next(root.rglob(regular_name), None)
            bold_path = next(root.rglob(bold_name), None)
            if regular_path and bold_path:
                return regular_path, bold_path
        if regular_path or bold_path:
            return regular_path or bold_path, bold_path or regular_path

    broad_roots = [*roots, Path("/System/Library/Fonts")]
    for prefix in ("Montserrat", "Inter"):
        candidates = [
            path
            for root in broad_roots
            if root.is_dir()
            for path in root.rglob(f"{prefix}*.ttf")
            if "variable" not in path.name.lower() and "italic" not in path.name.lower()
        ]
        regular = next(
            (path for path in candidates if "bold" not in path.name.lower()), None
        )
        bold = next(
            (
                path
                for path in candidates
                if "bold" in path.name.lower() and "semi" not in path.name.lower()
            ),
            None,
        )
        if regular and bold:
            return regular, bold
        if candidates:
            return candidates[0], candidates[0]
    return None, None


def register_fonts() -> tuple[str, str]:
    """Register optional local fonts and return paragraph-compatible names."""

    regular_path, bold_path = _discover_ttf_pair()
    regular_name, bold_name = "CVSans", "CVSansBd"
    try:
        registered = set(pdfmetrics.getRegisteredFontNames())
        if regular_path and regular_path.exists() and regular_name not in registered:
            pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
        if (
            bold_path
            and bold_path.exists()
            and bold_path.resolve()
            != (regular_path.resolve() if regular_path else None)
        ):
            if bold_name not in set(pdfmetrics.getRegisteredFontNames()):
                pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
        elif regular_path and regular_path.exists():
            bold_name = regular_name

        registered = set(pdfmetrics.getRegisteredFontNames())
        if regular_name in registered:
            return (
                regular_name,
                bold_name if bold_name in registered else regular_name,
            )
    except Exception:
        pass
    return "Helvetica", "Helvetica-Bold"


def _style(
    name: str,
    *,
    parent: ParagraphStyle,
    font_name: str,
    font_size: float,
    leading: float,
    text_color,
    space_before: float = 0,
    space_after: float = 0,
    left_indent: float = 0,
    first_line_indent: float = 0,
) -> ParagraphStyle:
    return ParagraphStyle(
        name,
        parent=parent,
        fontName=font_name,
        fontSize=font_size,
        leading=leading,
        textColor=text_color,
        spaceBefore=space_before,
        spaceAfter=space_after,
        leftIndent=left_indent,
        firstLineIndent=first_line_indent,
        alignment=TA_LEFT,
    )


def make_styles(font_regular: str, font_bold: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    return {
        "L_Section": _style(
            "L_Section",
            parent=base,
            font_name=font_bold,
            font_size=9,
            leading=11,
            text_color=NAVY,
            space_after=5,
        ),
        "L_Body": _style(
            "L_Body",
            parent=base,
            font_name=font_regular,
            font_size=8.6,
            leading=10.3,
            text_color=BODY,
            space_after=3,
        ),
        "L_Skill": _style(
            "L_Skill",
            parent=base,
            font_name=font_regular,
            font_size=8.4,
            leading=10.1,
            text_color=BODY,
            space_after=4,
        ),
        "R_Name": _style(
            "R_Name",
            parent=base,
            font_name=font_bold,
            font_size=22,
            leading=24,
            text_color=NAVY,
            space_after=2,
        ),
        "R_Sub": _style(
            "R_Sub",
            parent=base,
            font_name=font_regular,
            font_size=9.5,
            leading=11.4,
            text_color=MUTED,
            space_after=5,
        ),
        "R_Section": _style(
            "R_Section",
            parent=base,
            font_name=font_bold,
            font_size=11,
            leading=13,
            text_color=NAVY,
            space_before=8,
            space_after=4,
        ),
        "R_Body": _style(
            "R_Body",
            parent=base,
            font_name=font_regular,
            font_size=9.3,
            leading=11.2,
            text_color=BODY,
            space_after=6,
        ),
        "R_Role": _style(
            "R_Role",
            parent=base,
            font_name=font_bold,
            font_size=9,
            leading=10.5,
            text_color=NAVY,
            space_before=5,
            space_after=2,
        ),
        "R_Bullet": _style(
            "R_Bullet",
            parent=base,
            font_name=font_regular,
            font_size=9.1,
            leading=10.7,
            text_color=BODY,
            space_after=2,
            left_indent=10,
            first_line_indent=-10,
        ),
        "P_Heading": _style(
            "P_Heading",
            parent=base,
            font_name=font_bold,
            font_size=10,
            leading=11.3,
            text_color=NAVY,
            space_before=5,
            space_after=3,
        ),
        "P_Body": _style(
            "P_Body",
            parent=base,
            font_name=font_regular,
            font_size=8.7,
            leading=10.4,
            text_color=BODY,
            space_after=3,
        ),
        "P_Contact": _style(
            "P_Contact",
            parent=base,
            font_name=font_regular,
            font_size=9,
            leading=11,
            text_color=BODY,
            space_after=4,
        ),
        "P_ExpRole": _style(
            "P_ExpRole",
            parent=base,
            font_name=font_bold,
            font_size=9.1,
            leading=10.4,
            text_color=NAVY,
            space_before=4,
            space_after=2,
        ),
        "P_ListLine": _style(
            "P_ListLine",
            parent=base,
            font_name=font_regular,
            font_size=8.7,
            leading=10.3,
            text_color=BODY,
            space_after=1,
        ),
        "P_ExpBullet": _style(
            "P_ExpBullet",
            parent=base,
            font_name=font_regular,
            font_size=8.7,
            leading=10.3,
            text_color=BODY,
            space_after=1,
            left_indent=10,
            first_line_indent=-10,
        ),
        "P_Name": _style(
            "P_Name",
            parent=base,
            font_name=font_bold,
            font_size=17,
            leading=20,
            text_color=NAVY,
            space_after=4,
        ),
    }


def compact_visual_styles(
    styles: dict[str, ParagraphStyle],
) -> dict[str, ParagraphStyle]:
    """Return a readable, vertically tighter copy of visual-column styles."""

    compact = dict(styles)
    overrides = {
        "R_Name": {"fontSize": 20.5, "leading": 22, "spaceAfter": 1},
        "R_Sub": {"fontSize": 9.2, "leading": 10.5, "spaceAfter": 3},
        "R_Section": {
            "fontSize": 10.5,
            "leading": 12,
            "spaceBefore": 5,
            "spaceAfter": 3,
        },
        "R_Body": {"fontSize": 9, "leading": 10.3, "spaceAfter": 4},
        "R_Role": {
            "fontSize": 8.8,
            "leading": 9.8,
            "spaceBefore": 3,
            "spaceAfter": 1,
        },
        "R_Bullet": {"fontSize": 8.8, "leading": 9.8, "spaceAfter": 1},
    }
    for key, values in overrides.items():
        compact[key] = ParagraphStyle(
            f"{key}_Compact",
            parent=styles[key],
            **values,
        )
    return compact
