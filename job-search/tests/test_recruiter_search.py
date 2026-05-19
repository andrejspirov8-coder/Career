"""Tests for merged LinkedIn People-search query lists."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import recruiter_search as rs  # noqa: E402


class TestRecruiterSearch(unittest.TestCase):
    def test_classify_query_intent(self) -> None:
        self.assertEqual(
            rs.classify_query_intent("recruiter luxury retail Vilnius"), "recruiter"
        )
        self.assertEqual(
            rs.classify_query_intent("area manager retail Vilnius"), "hiring_leader"
        )

    def test_merged_queries_include_persona_lines(self) -> None:
        cfg = {
            "search": {
                "default_geo_keyword": "Lithuania",
                "queries_by_variant": {
                    "luxury-retail": ["recruiter luxury retail Vilnius"],
                },
            },
            "hiring_network": {
                "persona_search_queries": {
                    "luxury-retail": ["store director premium fashion Vilnius"],
                },
            },
        }
        merged = rs.merged_queries_for_variant(cfg, "luxury-retail")
        queries = [q for q, _ in merged]
        intents = {i for _, i in merged}
        self.assertIn("store director premium fashion Vilnius Lithuania", queries)
        self.assertIn("recruiter", intents)
        self.assertIn("hiring_leader", intents)

    def test_geo_appended_once(self) -> None:
        cfg = {
            "search": {
                "default_geo_keyword": "Lithuania",
                "queries_by_variant": {"it-business": ["HR manager IT Lithuania"]},
            },
            "hiring_network": {"persona_search_queries": {}},
        }
        merged = rs.merged_queries_for_variant(cfg, "it-business")
        self.assertEqual(merged[0][0].lower().count("lithuania"), 1)


if __name__ == "__main__":
    unittest.main()
