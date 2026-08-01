from __future__ import annotations

from career_job_search.recruiters.outreach import (
    build_personalized_connection_note,
    evidence_phrase_for_outreach,
    first_name_from_display,
    pick_template_for_profile,
)


def test_first_name_from_display_simple() -> None:
    assert first_name_from_display("Jane Doe") == "Jane"


def test_first_name_from_display_with_punctuation() -> None:
    assert first_name_from_display("Dr. Jane, PhD") == "Dr"


def test_first_name_from_display_empty() -> None:
    assert first_name_from_display("") == "there"


def test_first_name_from_display_only_punctuation() -> None:
    assert first_name_from_display(";;;") == "there"


def test_evidence_phrase_uses_persona_evidence() -> None:
    phrase = evidence_phrase_for_outreach(
        headline="",
        company="",
        about="",
        signals_csv="",
        persona_evidence="expert in data science at Google",
    )
    assert len(phrase) > 0
    assert "data science" in phrase


def test_evidence_phrase_falls_back_to_headline() -> None:
    phrase = evidence_phrase_for_outreach(
        headline="Senior Software Engineer at Meta",
        company="Meta",
        about="",
        signals_csv="",
        persona_evidence="",
    )
    assert "Senior" in phrase


def test_evidence_phrase_falls_back_to_company() -> None:
    phrase = evidence_phrase_for_outreach(
        headline="",
        company="Acme Corp",
        about="",
        signals_csv="",
        persona_evidence="",
    )
    assert "Acme" in phrase


def test_evidence_phrase_final_fallback() -> None:
    phrase = evidence_phrase_for_outreach(
        headline="",
        company="",
        about="",
        signals_csv="",
        persona_evidence="",
    )
    assert phrase == "your field"


def test_evidence_phrase_generic_headline_not_used() -> None:
    phrase = evidence_phrase_for_outreach(
        headline="Recruiter",
        company="",
        about="",
        signals_csv="",
        persona_evidence="",
    )
    assert "Recruiter" not in phrase
    assert phrase == "your field"


def test_build_personalized_connection_note_basic() -> None:
    result = build_personalized_connection_note(
        "Hi {first_name}, I loved your work!",
        first_name="Jane",
        profile_phrase="",
        max_chars=280,
    )
    assert "Jane" in result
    assert len(result) <= 280


def test_build_personalized_connection_note_with_phrase() -> None:
    result = build_personalized_connection_note(
        "Hi {first_name},",
        first_name="Jane",
        profile_phrase="great profile",
        max_chars=280,
    )
    assert "(great profile)" in result


def test_build_personalized_connection_note_truncates() -> None:
    long_template = "Hi {first_name}, " + "x" * 300
    result = build_personalized_connection_note(
        long_template,
        first_name="Jane",
        profile_phrase="",
        max_chars=100,
    )
    assert len(result) <= 100


def test_pick_template_for_profile_prefers_lt() -> None:
    templates = {
        "luxury-retail": "Standard template",
        "luxury-retail-lt": "Lithuanian template",
    }
    result = pick_template_for_profile(
        "luxury-retail",
        note_templates=templates,
        prefer_lt=True,
    )
    assert result == "Lithuanian template"


def test_pick_template_for_profile_standard() -> None:
    templates = {"business-process": "BP template"}
    result = pick_template_for_profile(
        "business-process",
        note_templates=templates,
        prefer_lt=False,
    )
    assert result == "BP template"


def test_pick_template_for_profile_missing() -> None:
    result = pick_template_for_profile(
        "unknown",
        note_templates={},
        prefer_lt=False,
    )
    assert result == ""
