"""Mocked tests for Ollama recruiter agents (no live Ollama required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from recruiter_ollama_agents import (  # noqa: E402
    CompanyAnalysis,
    DiscoveryBatchResult,
    DiscoveryExtraction,
    OutreachNote,
    SupervisorDecision,
    analyze_company,
    extract_discovery_batch,
    polish_outreach_note,
    supervise_row,
)
from recruiter_ollama_client import (  # noqa: E402
    agent_enabled,
    health_check,
    llm_enabled,
    resolve_chat_model,
)
from recruiter_ollama_embed import blend_cv_score  # noqa: E402
from recruiter_web_research import WebSearchHit  # noqa: E402


def _sample_cfg(*, enabled: bool = True) -> dict:
    return {
        "llm": {
            "enabled": enabled,
            "default_chat_model": "qwen3.5:35b-a3b-fast",
            "fallback_to_rules": True,
            "agents": {
                "discovery": {"enabled": True, "batch_hits": True},
                "company_analyst": {"enabled": True},
                "outreach_writer": {"enabled": True},
                "supervisor": {
                    "enabled": True,
                    "model": "qwen3.5:35b-a3b-fast",
                    "heavy_model": "qwen3.6:latest",
                },
            },
            "embed": {"enabled": False, "cv_blend_weight": 0.3},
        }
    }


class TestOllamaConfig(unittest.TestCase):
    def test_llm_disabled_via_flag(self) -> None:
        cfg = _sample_cfg(enabled=True)
        self.assertTrue(llm_enabled(cfg))
        cfg["llm"]["enabled"] = False
        self.assertFalse(llm_enabled(cfg))
        self.assertFalse(agent_enabled(cfg, "discovery"))

    def test_resolve_chat_model_agent_override(self) -> None:
        cfg = _sample_cfg()
        self.assertEqual(resolve_chat_model(cfg, "supervisor"), "qwen3.5:35b-a3b-fast")
        cfg["llm"]["agents"]["supervisor"]["model"] = "custom-model"
        self.assertEqual(resolve_chat_model(cfg, "supervisor"), "custom-model")


class TestPydanticSchemas(unittest.TestCase):
    def test_outreach_note_truncates_over_280(self) -> None:
        long = "Hi Jane, " + ("x" * 300)
        note = OutreachNote(note=long, evidence_cited="Area Manager at Apranga")
        self.assertLessEqual(len(note.note), 280)

    def test_supervisor_decision_enum(self) -> None:
        d = SupervisorDecision(action="review", reason="borderline sector")
        self.assertEqual(d.action, "review")


class TestDiscoveryAgentMocked(unittest.TestCase):
    @patch("recruiter_ollama_agents.invoke_structured")
    def test_batch_extraction(self, mock_invoke: MagicMock) -> None:
        mock_invoke.return_value = DiscoveryBatchResult(
            candidates=[
                DiscoveryExtraction(
                    name="Lina Area",
                    headline="Area Manager premium retail",
                    company="Apranga",
                    profile_url="https://www.linkedin.com/in/lina-area/",
                    discovery_notes="Vilnius luxury retail leader",
                    relevance_0_100=78,
                )
            ]
        )
        hits = [
            WebSearchHit(
                title="Lina Area - Area Manager",
                url="https://www.linkedin.com/in/lina-area/",
                snippet="Premium retail Vilnius",
            )
        ]
        out = extract_discovery_batch(
            hits, variant_slug="luxury-retail", full_cfg=_sample_cfg()
        )
        self.assertEqual(len(out), 1)
        self.assertIn("linkedin.com/in/", out[0].profile_url)

    @patch("recruiter_ollama_agents.invoke_structured")
    def test_fallback_when_llm_returns_none(self, mock_invoke: MagicMock) -> None:
        mock_invoke.return_value = None
        hits = [WebSearchHit(title="Test", url="https://example.com", snippet="x")]
        out = extract_discovery_batch(
            hits, variant_slug="luxury-retail", full_cfg=_sample_cfg()
        )
        self.assertEqual(out, [])


class TestCompanyAnalystMocked(unittest.TestCase):
    @patch("recruiter_ollama_agents.invoke_structured")
    def test_analyze_company(self, mock_invoke: MagicMock) -> None:
        mock_invoke.return_value = CompanyAnalysis(
            relevance_0_100=72,
            flags=["track_aligned"],
            rationale="Premium fashion retailer in Vilnius",
            recommended_status="approved",
        )
        result = analyze_company(
            company="Apranga",
            headline="Area Manager",
            web_blob="luxury fashion retail Lithuania",
            full_cfg=_sample_cfg(),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertGreaterEqual(result.relevance_0_100, 70)


class TestOutreachWriterMocked(unittest.TestCase):
    @patch("recruiter_ollama_agents.invoke_structured")
    def test_polish_note(self, mock_invoke: MagicMock) -> None:
        mock_invoke.return_value = OutreachNote(
            note="Hi Lina, I am exploring premium retail leadership around Vilnius. "
            "Would value connecting given your work as Area Manager at Apranga.",
            evidence_cited="Area Manager at Apranga",
        )
        result = polish_outreach_note(
            draft_note="Hi Lina, generic note.",
            name="Lina Area",
            headline="Area Manager",
            company="Apranga",
            persona="hiring_manager",
            cv_variant="luxury-retail",
            full_cfg=_sample_cfg(),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertLessEqual(len(result.note), 280)
        self.assertIn("Apranga", result.note)


class TestSupervisorMocked(unittest.TestCase):
    @patch("recruiter_ollama_agents.invoke_structured")
    def test_supervise_row_uses_heavy_model_flag(self, mock_invoke: MagicMock) -> None:
        mock_invoke.return_value = SupervisorDecision(
            action="approved", reason="clear retail fit"
        )
        row = {
            "name": "Test",
            "validation_status": "review",
            "company_relevance_score": "65",
            "_use_heavy_supervisor": "true",
        }
        decision = supervise_row(row, full_cfg=_sample_cfg())
        self.assertIsNotNone(decision)
        call_cfg = mock_invoke.call_args[0][0]
        sup_model = call_cfg["llm"]["agents"]["supervisor"]["model"]
        self.assertEqual(sup_model, "qwen3.6:latest")


class TestEmbedBlend(unittest.TestCase):
    def test_blend_without_embed_returns_keyword_score(self) -> None:
        cfg = _sample_cfg()
        cfg["llm"]["embed"]["enabled"] = False
        score = blend_cv_score(75.0, "Area Manager retail", "luxury-retail", cfg)
        self.assertEqual(score, 75.0)


class TestHealthCheck(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_health_check_ok(self, mock_urlopen: MagicMock) -> None:
        resp = MagicMock()
        resp.read.return_value = b'{"models":[{"name":"qwen3.5:35b-a3b-fast"}]}'
        resp.__enter__.return_value = resp
        mock_urlopen.return_value = resp
        ok, msg = health_check("http://127.0.0.1:11434")
        self.assertTrue(ok)
        self.assertIn("ollama ok", msg)


class TestNoLlmPipeline(unittest.TestCase):
    @patch("recruiter_ollama_agents.invoke_structured")
    def test_disabled_llm_skips_agents(self, mock_invoke: MagicMock) -> None:
        cfg = _sample_cfg(enabled=False)
        hits = [WebSearchHit(title="T", url="https://linkedin.com/in/x/", snippet="s")]
        self.assertEqual(
            extract_discovery_batch(hits, variant_slug="luxury-retail", full_cfg=cfg),
            [],
        )
        mock_invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
