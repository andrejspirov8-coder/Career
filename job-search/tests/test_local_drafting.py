from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import local_drafting as drafting
from opportunity_models import OpportunityEvidence


def test_local_drafting_defaults_off_and_uses_loopback_only(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(
        drafting,
        "ollama_health",
        lambda: {
            "online": False,
            "models": [],
            "base_url": drafting.OLLAMA_BASE_URL,
            "message": "offline",
        },
    )

    status = drafting.drafting_status(tmp_path / "missing.json")

    assert status["enabled"] is False
    assert status["network_scope"] == "127.0.0.1 only"
    assert drafting.OLLAMA_CHAT_URL.startswith("http://127.0.0.1:")
    assert status["automatic_actions"] is False


def test_enabling_requires_an_installed_local_model(tmp_path: Path, monkeypatch):
    path = tmp_path / "ai_preferences.json"
    monkeypatch.setattr(
        drafting,
        "ollama_health",
        lambda: {
            "online": True,
            "models": ["small-local:latest"],
            "base_url": drafting.OLLAMA_BASE_URL,
            "message": "online",
        },
    )

    with pytest.raises(ValueError, match="installed"):
        drafting.update_preferences({"enabled": True, "model": "missing:latest"}, path)

    saved = drafting.update_preferences(
        {"enabled": True, "model": "small-local:latest"}, path
    )
    assert saved.enabled is True
    assert path.stat().st_mode & 0o777 == 0o600


def test_draft_is_blocked_until_user_enables_it(tmp_path: Path):
    with pytest.raises(PermissionError, match="Enable it in Settings"):
        drafting.generate_draft(
            {
                "opportunity_id": "opp_test",
                "draft_type": "cover_letter",
                "instructions": "",
            },
            tmp_path / "missing.json",
        )


def test_draft_uses_local_context_and_returns_review_warning(
    tmp_path: Path, monkeypatch
):
    preferences = drafting.DraftingPreferences(enabled=True, model="small-local:latest")
    drafting.save_preferences(preferences, tmp_path / "ai_preferences.json")
    opportunity = SimpleNamespace(
        title="Operations Manager",
        company="Example",
        location="Vilnius",
        description="Improve service operations and partner performance.",
        salary_text="",
        deadline="",
        match=SimpleNamespace(
            best_variant="operations-management",
            keyword_hits=["service operations"],
            missing_keywords=[],
        ),
        evidence=OpportunityEvidence(
            cv_fit_evidence=["Managed cross-functional teams"]
        ),
    )
    monkeypatch.setattr(
        drafting, "get_opportunity", lambda _opportunity_id: opportunity
    )
    monkeypatch.setattr(
        drafting, "_variant_markdown", lambda _variant: "Verified CV facts"
    )
    captured: dict[str, str] = {}

    def fake_chat(*, model: str, system_prompt: str, user_prompt: str) -> str:
        captured.update(model=model, system=system_prompt, user=user_prompt)
        return "Dear Hiring Team,\n\nA truthful local draft."

    monkeypatch.setattr(drafting, "_ollama_chat", fake_chat)

    result = drafting.generate_draft(
        {
            "opportunity_id": "opp_test",
            "draft_type": "cover_letter",
            "instructions": "Keep it direct.",
        },
        tmp_path / "ai_preferences.json",
    )

    assert result["text"].startswith("Dear Hiring Team")
    assert result["privacy"]["sent_to"] == "http://127.0.0.1:11434"
    assert result["privacy"]["stored_by_dashboard"] is False
    assert "Never invent" in captured["system"]
    assert "Verified CV facts" in captured["user"]
    assert result["warning"].startswith("Review every claim")


def test_draft_request_rejects_paths_and_unknown_fields():
    with pytest.raises(ValueError):
        drafting.DraftRequest.model_validate(
            {
                "opportunity_id": "../../state/opportunities.sqlite3",
                "draft_type": "cover_letter",
            }
        )
    with pytest.raises(ValueError):
        drafting.DraftRequest.model_validate(
            {
                "opportunity_id": "opp_test",
                "draft_type": "cover_letter",
                "extra": "not allowed",
            }
        )
