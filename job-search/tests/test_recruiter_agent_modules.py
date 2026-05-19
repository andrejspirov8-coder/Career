"""Tests for agent context, validators, tools, prompts, and tool-calling loop."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from recruiter_agent_context import outreach_context, supervisor_context  # noqa: E402
from recruiter_agent_tools import (  # noqa: E402
    _tool_count_chars,
    _tool_lookup_persona_stats,
    dispatch_tool_call,
    tools_for_agent,
)
from recruiter_agent_validators import (  # noqa: E402
    validate_outreach_note,
    validate_supervisor_decision,
)
from recruiter_ollama_agents import (  # noqa: E402
    CompanyAnalysis,
    OutreachNote,
    SupervisorDecision,
    agent_system_prompt,
    analyze_company,
    polish_outreach_note,
)
from recruiter_ollama_client import (  # noqa: E402
    invoke_with_tools,
    prompt_version,
    reset_circuit_breaker,
)


def _sample_cfg(*, use_tools: bool = False) -> dict:
    return {
        "llm": {
            "enabled": True,
            "fallback_to_rules": True,
            "retry_enabled": True,
            "agents": {
                "outreach_writer": {
                    "enabled": True,
                    "use_tools": use_tools,
                    "tools": ["count_chars", "get_cv_blurb"],
                    "max_tool_turns": 3,
                },
                "supervisor": {
                    "enabled": True,
                    "use_tools": use_tools,
                    "tools": ["lookup_company_history", "lookup_persona_stats"],
                },
                "company_analyst": {"enabled": True},
            },
        }
    }


class TestAgentContext(unittest.TestCase):
    @patch("recruiter_agent_context.load_persona_stats")
    @patch("recruiter_agent_context.cv_context_blob")
    def test_outreach_context_includes_cv_excerpt_and_persona_rate(
        self, mock_cv: MagicMock, mock_stats: MagicMock
    ) -> None:
        mock_cv.return_value = "Luxury retail leadership in Vilnius"
        mock_stats.return_value = {
            "retail_area_leader": {"sent": 10, "accepted": 6, "rate": 0.6}
        }
        ctx = outreach_context(
            name="Lina",
            headline="Area Manager",
            company="Apranga",
            persona="retail_area_leader",
            cv_variant="luxury-retail",
            evidence=["area manager"],
        )
        self.assertIn("Luxury retail", ctx["cv_excerpt"])
        self.assertEqual(ctx["persona_accept_rate"], 0.6)
        self.assertEqual(ctx["top_evidence"], ["area manager"])

    def test_supervisor_context_blocks_hard_flag_approval(self) -> None:
        ctx = supervisor_context(
            {
                "company": "Staffing Co",
                "company_flags": "staffing_only,outreach_exclude_term",
                "company_relevance_score": "72",
                "persona": "recruiter_hr",
            },
            full_cfg={},
        )
        self.assertIn("staffing_only", ctx["hard_flags"])


class TestAgentValidators(unittest.TestCase):
    def test_validate_outreach_note_rejects_generic(self) -> None:
        ok, issues = validate_outreach_note(
            "Hi Jane, your work looked relevant.",
            name="Jane",
            evidence="your work",
        )
        self.assertFalse(ok)
        self.assertIn("generic_evidence", issues)

    def test_validate_supervisor_decision_overrides_approve_on_hard_flag(self) -> None:
        decision = SupervisorDecision(action="approved", reason="looks fine")
        row = {"company_flags": "staffing_only", "company_relevance_score": "80"}
        ok, issues = validate_supervisor_decision(decision, row)
        self.assertFalse(ok)
        self.assertIn("approve_with_hard_flag", issues)


class TestCompanyAnalystValidator(unittest.TestCase):
    @patch("recruiter_ollama_agents.invoke_structured")
    def test_company_analyst_falls_back_when_validator_fails(
        self, mock_invoke: MagicMock
    ) -> None:
        mock_invoke.return_value = CompanyAnalysis.model_construct(
            relevance_0_100=88,
            recommended_status="maybe",
            rationale="invalid enum",
        )
        result = analyze_company(
            company="Apranga",
            headline="Retail",
            web_blob="Premium fashion",
            full_cfg=_sample_cfg(),
        )
        self.assertIsNone(result)


class TestAgentTools(unittest.TestCase):
    def test_tool_dispatch_unknown_name_returns_error_string(self) -> None:
        out = dispatch_tool_call({"name": "missing_tool", "args": {}}, [])
        self.assertIn("unknown tool", out)

    def test_count_chars_tool(self) -> None:
        self.assertEqual(_tool_count_chars("Hi  Jane"), "7")

    @patch("recruiter_agent_tools.load_persona_stats")
    def test_lookup_persona_stats_tool(self, mock_stats: MagicMock) -> None:
        mock_stats.return_value = {
            "hiring_manager": {"sent": 3, "accepted": 1, "rate": 0.33}
        }
        raw = _tool_lookup_persona_stats("hiring_manager")
        self.assertIn("0.33", raw)


class TestInvokeWithTools(unittest.TestCase):
    def setUp(self) -> None:
        reset_circuit_breaker()

    @patch("recruiter_ollama_client._chat_ollama")
    @patch("recruiter_ollama_client._invoke_with_retry")
    def test_invoke_with_tools_routes_tool_call_then_returns_structured(
        self, mock_retry: MagicMock, mock_chat: MagicMock
    ) -> None:
        tool_resp = MagicMock()
        tool_resp.tool_calls = [
            {"name": "count_chars", "args": {"text": "hello"}, "id": "call-1"}
        ]
        tool_resp.content = ""
        final_resp = MagicMock()
        final_resp.tool_calls = []
        final_resp.content = (
            '{"note": "Hi Jane, great fit.", "evidence_cited": "Area Manager"}'
        )

        llm_bound = MagicMock()
        llm_bound.bind_tools.return_value = llm_bound
        llm_bound.invoke.side_effect = [tool_resp]
        llm_plain = MagicMock()
        structured = MagicMock()
        structured.invoke.return_value = OutreachNote(
            note="Hi Jane, great fit.", evidence_cited="Area Manager"
        )
        llm_plain.with_structured_output.return_value = structured
        mock_chat.side_effect = [llm_bound, llm_plain]

        def retry_side_effect(fn, **kwargs):
            return fn()

        mock_retry.side_effect = retry_side_effect

        cfg = _sample_cfg(use_tools=True)
        tools = tools_for_agent(cfg, "outreach_writer")
        result = invoke_with_tools(
            cfg,
            "outreach_writer",
            "system",
            "user",
            OutreachNote,
            tools,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("Jane", result.note)

    @patch("recruiter_ollama_client.invoke_structured")
    @patch("recruiter_ollama_client._chat_ollama")
    def test_supervisor_falls_back_to_invoke_structured_when_bind_tools_unsupported(
        self, mock_chat: MagicMock, mock_structured: MagicMock
    ) -> None:
        mock_chat.return_value.bind_tools.side_effect = RuntimeError("no tools")
        mock_structured.return_value = SupervisorDecision(
            action="review", reason="fallback"
        )
        cfg = _sample_cfg(use_tools=True)
        tools = tools_for_agent(cfg, "supervisor")
        result = invoke_with_tools(
            cfg,
            "supervisor",
            "system",
            "user",
            SupervisorDecision,
            tools,
        )
        self.assertEqual(result.action, "review")
        mock_structured.assert_called_once()

    @patch("recruiter_llm_trace.emit_event")
    @patch("recruiter_ollama_client._chat_ollama")
    @patch("recruiter_ollama_client._invoke_with_retry")
    def test_tool_call_event_appears_in_trace(
        self, mock_retry: MagicMock, mock_chat: MagicMock, mock_emit: MagicMock
    ) -> None:
        tool_resp = MagicMock()
        tool_resp.tool_calls = [
            {"name": "count_chars", "args": {"text": "x"}, "id": "t1"}
        ]
        tool_resp.content = ""
        no_tools_resp = MagicMock()
        no_tools_resp.tool_calls = []
        no_tools_resp.content = ""
        llm_bound = MagicMock()
        llm_bound.bind_tools.return_value = llm_bound
        llm_bound.invoke.side_effect = [tool_resp, no_tools_resp]
        llm_plain = MagicMock()
        structured = MagicMock()
        structured.invoke.return_value = OutreachNote(
            note="Hi Jane, note.", evidence_cited="role"
        )
        llm_plain.with_structured_output.return_value = structured
        mock_chat.side_effect = [llm_bound, llm_plain]
        mock_retry.side_effect = lambda fn, **kw: fn()

        cfg = _sample_cfg(use_tools=True)
        invoke_with_tools(
            cfg,
            "outreach_writer",
            "system prompt",
            "user prompt",
            OutreachNote,
            tools_for_agent(cfg, "outreach_writer"),
        )
        kinds = [call.kwargs.get("kind") for call in mock_emit.call_args_list]
        self.assertIn("tool_call", kinds)


class TestOutreachWriterToolsConfig(unittest.TestCase):
    @patch("recruiter_ollama_agents.invoke_with_tools")
    @patch("recruiter_ollama_agents.agent_enabled")
    def test_outreach_writer_uses_tools_when_configured(
        self, mock_enabled: MagicMock, mock_tools: MagicMock
    ) -> None:
        mock_enabled.return_value = True
        mock_tools.return_value = OutreachNote(
            note="Hi Lina, your Area Manager work at Apranga stood out.",
            evidence_cited="Area Manager at Apranga",
        )
        cfg = _sample_cfg(use_tools=True)
        result = polish_outreach_note(
            draft_note="Hi Lina, exploring roles.",
            name="Lina",
            headline="Area Manager Apranga",
            company="Apranga",
            persona="retail_area_leader",
            cv_variant="luxury-retail",
            full_cfg=cfg,
        )
        self.assertIsNotNone(result)
        mock_tools.assert_called_once()


class TestAgentPromptsYaml(unittest.TestCase):
    def test_agent_prompts_yaml_loads_all_four(self) -> None:
        for agent in ("discovery", "company_analyst", "outreach_writer", "supervisor"):
            prompt = agent_system_prompt(agent, f"fallback-{agent}")
            self.assertNotEqual(prompt, f"fallback-{agent}")
            self.assertGreater(len(prompt), 20)

    def test_prompt_version_appears_in_trace(self) -> None:
        system = agent_system_prompt("outreach_writer", "fallback")
        version = prompt_version(system)
        self.assertEqual(len(version), 8)


if __name__ == "__main__":
    unittest.main()
