"""Tests for LLM trace / verbose logging."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from career_job_search.recruiters.llm_trace import (  # noqa: E402
    AgentCallTrace,
    emit_event,
    trace_enabled,
    verbose_enabled,
)


class TestLlmTrace(unittest.TestCase):
    def test_verbose_and_trace_flags(self) -> None:
        cfg = {"llm": {"verbose": True, "trace": False}}
        self.assertTrue(verbose_enabled(cfg))
        self.assertFalse(trace_enabled(cfg))

    def test_emit_event_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            cfg = {
                "llm": {
                    "verbose": False,
                    "trace": True,
                    "trace_path": str(path),
                }
            }
            emit_event(
                cfg,
                kind="agent_call",
                agent="outreach_writer",
                model="qwen3.5:35b-a3b-fast",
                ok=True,
                user_prompt="Hi Jane",
                output={"note": "Hello"},
            )
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["agent"], "outreach_writer")
            self.assertEqual(row["output"]["note"], "Hello")

    @patch("career_job_search.recruiters.llm_trace._print_event")
    def test_agent_call_trace_success(self, mock_print) -> None:
        cfg = {"llm": {"verbose": True, "trace": False}}
        with AgentCallTrace(
            cfg,
            agent="discovery",
            model="qwen3.5:35b-a3b-fast",
            system_prompt="sys",
            user_prompt="user payload",
        ) as trace:
            trace.success({"name": "Jane"})
        mock_print.assert_called()


if __name__ == "__main__":
    unittest.main()
