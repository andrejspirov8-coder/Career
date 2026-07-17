"""Parse and validate the private Markdown CV source format."""

from __future__ import annotations

from pathlib import Path

ParsedCv = tuple[
    str,
    str,
    str,
    str,
    str,
    list[str],
    str,
    list[str],
    list[str],
    list[tuple[str, list[str]]],
]


def validate_cv_markdown(lines: list[str]) -> None:
    if not lines:
        raise ValueError("CV markdown is empty.")
    if not lines[0].startswith("# "):
        raise ValueError("First line must be `# Name`.")


def parse_cv_markdown(md_path: Path) -> ParsedCv:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    validate_cv_markdown(lines)
    index = 0

    name = lines[index][2:].strip()
    index += 1
    while index < len(lines) and not lines[index].strip():
        index += 1

    contact_chunks: list[str] = []
    while index < len(lines) and not lines[index].startswith("## "):
        text = lines[index].strip()
        if text and text != "---":
            contact_chunks.append(text)
        index += 1
    contact = " ".join(contact_chunks)

    summary = ""
    target_title = "LUXURY RETAIL LEADER"
    document_language = "en"
    recent_focus = ""
    selected_achievements: list[str] = []
    experience: list[tuple[str, list[str]]] = []
    skills: list[str] = []
    languages: list[str] = []

    while index < len(lines):
        line = lines[index]
        if not line.startswith("## "):
            index += 1
            continue
        title = line[3:].strip()
        index += 1
        body_lines: list[str] = []
        while index < len(lines) and not lines[index].startswith("## "):
            body_lines.append(lines[index])
            index += 1
        body = [line for line in body_lines if line.strip() and line.strip() != "---"]

        if title == "Document Language":
            document_language = (
                " ".join(line.strip() for line in body if line.strip()) or "en"
            ).lower()
        elif title == "Target Title":
            target_title = (
                " ".join(line.strip() for line in body if line.strip()) or target_title
            )
        elif title == "Professional Summary":
            summary = " ".join(line.strip() for line in body if line.strip())
        elif title == "Selected Achievements":
            selected_achievements.extend(
                line.strip()[2:].strip()
                for line in body
                if line.strip().startswith("- ")
            )
        elif title == "Recent Focus":
            recent_focus = " ".join(line.strip() for line in body if line.strip())
        elif title == "Experience":
            item_index = 0
            while item_index < len(body):
                stripped = body[item_index].strip()
                if not stripped.startswith("###"):
                    item_index += 1
                    continue
                heading = stripped.lstrip("#").strip()
                bullets: list[str] = []
                item_index += 1
                while item_index < len(body) and body[item_index].strip().startswith(
                    "- "
                ):
                    bullets.append(body[item_index].strip()[2:].strip())
                    item_index += 1
                experience.append((heading, bullets))
        elif title in {"Technical Skills", "Core Skills", "Skills"}:
            skills.extend(
                line.strip()[2:].strip()
                for line in body
                if line.strip().startswith("- ")
            )
        elif title == "Languages":
            languages.extend(
                line.strip()[2:].strip()
                for line in body
                if line.strip().startswith("- ")
            )

    if not summary:
        raise ValueError("Missing `## Professional Summary` section in CV markdown.")
    if not experience:
        raise ValueError("Missing `## Experience` section in CV markdown.")

    return (
        name,
        contact,
        target_title,
        document_language,
        summary,
        selected_achievements,
        recent_focus,
        skills,
        languages,
        experience,
    )


def labels_for_language(document_language: str) -> dict[str, str]:
    if document_language.startswith("lt"):
        return {
            "contact": "KONTAKTAI",
            "skills": "ĮGŪDŽIAI",
            "languages": "KALBOS",
            "profile": "PROFILIS",
            "recent_focus": "DABARTINIS TIKSLAS",
            "experience": "PATIRTIS",
            "summary": "PROFESINĖ SANTRAUKA",
            "selected_achievements": "ATRINKTI PASIEKIMAI",
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
        "selected_achievements": "SELECTED ACHIEVEMENTS",
        "key_skills": "KEY SKILLS",
    }


def contact_lines(contact: str) -> list[str]:
    parts = [part.strip() for part in contact.split("|") if part.strip()]
    return parts if parts else [contact]
