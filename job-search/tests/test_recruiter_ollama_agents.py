"""Mocked tests for Ollama recruiter agents (no live Ollama required)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from career_job_search.recruiters.ollama_agents import (
    OUTREACH_SYSTEM,
    SUPERVISOR_SYSTEM,
    CompanyAnalysis,
    DiscoveryBatchResult,
    DiscoveryExtraction,
    OutreachNote,
    SupervisorDecision,
    _prompts_raw,
    agent_few_shot_messages,
    agent_system_prompt,
    analyze_company,
    extract_discovery_batch,
    polish_outreach_note,
    supervise_row,
)
from career_job_search.recruiters.ollama_client import (
    agent_enabled,
    health_check,
    llm_enabled,
    resolve_chat_model,
)
from career_job_search.recruiters.ollama_embed import blend_cv_score
from career_job_search.recruiters.web_research import WebSearchHit


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
    @patch("career_job_search.recruiters.ollama_agents.invoke_structured")
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

    @patch("career_job_search.recruiters.ollama_agents.invoke_structured")
    def test_fallback_when_llm_returns_none(self, mock_invoke: MagicMock) -> None:
        mock_invoke.return_value = None
        hits = [WebSearchHit(title="Test", url="https://example.com", snippet="x")]
        out = extract_discovery_batch(
            hits, variant_slug="luxury-retail", full_cfg=_sample_cfg()
        )
        self.assertEqual(out, [])


class TestCompanyAnalystMocked(unittest.TestCase):
    @patch("career_job_search.recruiters.ollama_agents.invoke_structured")
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
    @patch("career_job_search.recruiters.ollama_agents.invoke_structured")
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
    @patch("career_job_search.recruiters.ollama_agents.invoke_structured")
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
    @patch("career_job_search.recruiters.ollama_agents.invoke_structured")
    def test_disabled_llm_skips_agents(self, mock_invoke: MagicMock) -> None:
        cfg = _sample_cfg(enabled=False)
        hits = [WebSearchHit(title="T", url="https://linkedin.com/in/x/", snippet="s")]
        self.assertEqual(
            extract_discovery_batch(hits, variant_slug="luxury-retail", full_cfg=cfg),
            [],
        )
        mock_invoke.assert_not_called()


class TestPromptParity(unittest.TestCase):
    """Ensure Python fallback prompts are consistent with YAML prompts."""

    def setUp(self) -> None:
        # Clear lru_cache so _prompts_raw reads fresh from disk
        from career_job_search.recruiters.ollama_agents import _prompts_raw

        _prompts_raw.cache_clear()

    def test_all_yaml_agents_have_fallback(self) -> None:
        """Every agent defined in YAML must have a corresponding Python fallback."""
        raw = _prompts_raw()
        yaml_agents = set(raw.keys())
        fallback_agents = {
            "discovery",
            "company_analyst",
            "outreach_writer",
            "supervisor",
        }
        missing = yaml_agents - fallback_agents
        self.assertEqual(
            missing,
            set(),
            f"YAML agents without Python fallback: {missing}",
        )

    def test_outreach_fallback_has_brand_rule(self) -> None:
        """OUTREACH_SYSTEM fallback should include the brand-drop rule from YAML."""
        self.assertIn("name-drop", OUTREACH_SYSTEM.lower())
        self.assertIn("non-retail", OUTREACH_SYSTEM.lower())

    def test_supervisor_fallback_has_cross_sector_logic(self) -> None:
        """SUPERVISOR_SYSTEM fallback should include cross-sector HR approval logic."""
        self.assertIn("cross-sector", SUPERVISOR_SYSTEM.lower())
        self.assertIn("in-house recruiter", SUPERVISOR_SYSTEM.lower())

    def test_few_shot_messages_have_unit_tests_presence(self) -> None:
        """agent_few_shot_messages should produce messages for agents with few_shot in YAML."""
        raw = _prompts_raw()
        for agent_name, block in raw.items():
            if not isinstance(block, dict):
                continue
            if block.get("few_shot"):
                messages = agent_few_shot_messages(agent_name)
                self.assertGreater(
                    len(messages),
                    0,
                    f"agent_few_shot_messages('{agent_name}') returned empty",
                )
                # Each pair is user + assistant
                self.assertEqual(
                    len(messages) % 2,
                    0,
                    f"few_shot for '{agent_name}' should have even count of messages",
                )

    def test_agent_system_prompt_uses_yaml_when_available(self) -> None:
        """agent_system_prompt should return YAML content when file exists."""
        raw = _prompts_raw()
        for agent_name, block in raw.items():
            if not isinstance(block, dict):
                continue
            yaml_system = (block.get("system") or "").strip()
            if not yaml_system:
                continue
            # Asking for this agent's prompt should return the YAML version
            result = agent_system_prompt(agent_name, "fallback text")
            self.assertEqual(
                result,
                yaml_system,
                f"agent_system_prompt('{agent_name}') returned YAML content",
            )

    def test_agent_system_prompt_falls_back(self) -> None:
        """agent_system_prompt should return fallback for unknown agent."""
        result = agent_system_prompt("nonexistent_agent", "custom fallback")
        self.assertEqual(result, "custom fallback")


if __name__ == "__main__":
    unittest.main()
