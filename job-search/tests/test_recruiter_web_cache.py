"""Tests for SQLite web search cache."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from recruiter_web_cache import get_cached, put  # noqa: E402
from recruiter_web_research import WebResearchResult, WebSearchHit  # noqa: E402


def _sample_result(query: str = "test query") -> WebResearchResult:
    return WebResearchResult(
        query=query,
        backend="offline_stub",
        hits=[
            WebSearchHit(
                title="Sample",
                url="https://www.linkedin.com/in/sample-person/",
                snippet="Retail leader",
                source="offline_stub",
            )
        ],
    )


class TestWebSearchCache(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cache_path = Path(self.tmp.name) / "cache.sqlite"
        self.full_cfg = {
            "web_discovery": {
                "cache_enabled": True,
                "cache_ttl_hours": 24,
                "cache_path": str(self.cache_path),
            }
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_cache_hit_returns_stored_payload(self) -> None:
        result = _sample_result("luxury retail Vilnius")
        put("luxury retail Vilnius", "offline_stub", result, cache_path=self.cache_path)
        cached = get_cached(
            "luxury retail Vilnius",
            "offline_stub",
            full_cfg=self.full_cfg,
            cache_path=self.cache_path,
        )
        self.assertIsNotNone(cached)
        assert cached is not None
        self.assertEqual(cached.query, result.query)
        self.assertEqual(len(cached.hits), 1)
        self.assertIn("sample-person", cached.hits[0].url)

    def test_cache_miss_falls_through_to_backend(self) -> None:
        cached = get_cached(
            "missing query",
            "offline_stub",
            full_cfg=self.full_cfg,
            cache_path=self.cache_path,
        )
        self.assertIsNone(cached)

    def test_ttl_expiry_forces_refetch(self) -> None:
        result = _sample_result("stale query")
        put("stale query", "offline_stub", result, cache_path=self.cache_path)
        stale_time = (datetime.now(UTC) - timedelta(hours=25)).replace(microsecond=0)
        import sqlite3

        with sqlite3.connect(str(self.cache_path)) as conn:
            conn.execute(
                "UPDATE searches SET fetched_at=? WHERE query=?",
                (stale_time.isoformat(), "stale query"),
            )
            conn.commit()
        cached = get_cached(
            "stale query",
            "offline_stub",
            full_cfg=self.full_cfg,
            cache_path=self.cache_path,
            ttl_hours=24,
        )
        self.assertIsNone(cached)

    @patch("recruiter_web_research.pick_backend")
    def test_web_search_uses_cache(self, mock_pick: MagicMock) -> None:
        from recruiter_web_research import web_search

        backend = MagicMock()
        backend.name = "offline_stub"
        mock_pick.return_value = backend
        result = _sample_result("cached web query")
        put(
            "cached web query site:linkedin.com/in Lithuania",
            "offline_stub",
            result,
            cache_path=self.cache_path,
        )
        cfg = {
            **self.full_cfg,
            "web_discovery": {
                **self.full_cfg["web_discovery"],
                "cache_path": str(self.cache_path),
            },
        }
        out = web_search(
            "cached web query site:linkedin.com/in Lithuania",
            backend="offline",
            full_cfg=cfg,
            use_cache=True,
        )
        self.assertEqual(out.query, result.query)
        backend.search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
