"""Tests for dispatch guard, Ollama retry/circuit breaker, persona stats."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import hiring_network_workflow as hn  # noqa: E402
from recruiter_dispatch_guard import is_stub_or_empty_row  # noqa: E402
from recruiter_ollama_client import (  # noqa: E402
    _invoke_with_retry,
    agent_enabled,
    reset_circuit_breaker,
)
from recruiter_persona_stats import (  # noqa: E402
    aggregate_persona_stats,
    persona_boost_factor,
    write_persona_stats,
)


class TestDispatchGuard(unittest.TestCase):
    def test_rejects_sample_linkedin_url(self) -> None:
        skip, reason = is_stub_or_empty_row(
            {
                "profile_url": "https://www.linkedin.com/in/sample-retail-leader/",
                "name": "Sample",
            }
        )
        self.assertTrue(skip)
        self.assertEqual(reason, "stub_url")

    def test_rejects_empty_identity(self) -> None:
        skip, reason = is_stub_or_empty_row(
            {
                "profile_url": "https://www.linkedin.com/in/anon/",
                "name": "",
                "headline": "",
                "company": "",
            }
        )
        self.assertTrue(skip)
        self.assertEqual(reason, "empty_identity")

    def test_rejects_offline_stub_backend(self) -> None:
        skip, reason = is_stub_or_empty_row(
            {
                "profile_url": "https://www.linkedin.com/in/real-person/",
                "name": "Real",
                "source_backend": "offline_stub",
            }
        )
        self.assertTrue(skip)
        self.assertEqual(reason, "offline_stub")


class TestApprovedInvitesGuard(unittest.TestCase):
    def _write_plan(self, rows: list[dict]) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        path = Path(tmp.name)
        for row in rows:
            tmp.write(json.dumps(row) + "\n")
        tmp.close()
        return path

    def test_full_auto_rejects_sample_linkedin_url(self) -> None:
        path = self._write_plan(
            [
                {
                    "profile_url": "https://www.linkedin.com/in/sample-retail-leader/",
                    "decision": "approved",
                    "send_tier": "auto_send",
                    "cv_variant": "luxury-retail",
                    "name": "Stub",
                },
                {
                    "profile_url": "https://www.linkedin.com/in/real-leader/",
                    "decision": "approved",
                    "send_tier": "auto_send",
                    "cv_variant": "luxury-retail",
                    "name": "Real",
                },
            ]
        )
        try:
            approved = hn._approved_invites_from_plan(
                path, tier="full_auto", max_profiles=None
            )
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(len(approved), 1)
        self.assertIn("real-leader", approved[0]["profile_url"])

    def test_full_auto_rejects_row_with_empty_identity(self) -> None:
        path = self._write_plan(
            [
                {
                    "profile_url": "https://www.linkedin.com/in/empty-row/",
                    "decision": "approved",
                    "send_tier": "auto_send",
                    "cv_variant": "luxury-retail",
                }
            ]
        )
        try:
            approved = hn._approved_invites_from_plan(
                path, tier="full_auto", max_profiles=None
            )
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(len(approved), 0)

    @patch("recruiter_dispatch_guard.load_already_sent_urls")
    def test_only_new_skips_already_sent_urls(self, mock_sent: MagicMock) -> None:
        mock_sent.return_value = {"https://www.linkedin.com/in/already-sent/"}
        path = self._write_plan(
            [
                {
                    "profile_url": "https://www.linkedin.com/in/already-sent/",
                    "decision": "approved",
                    "send_tier": "auto_send",
                    "cv_variant": "luxury-retail",
                    "name": "Old",
                },
                {
                    "profile_url": "https://www.linkedin.com/in/fresh-lead/",
                    "decision": "approved",
                    "send_tier": "auto_send",
                    "cv_variant": "luxury-retail",
                    "name": "Fresh",
                },
            ]
        )
        try:
            approved = hn._approved_invites_from_plan(
                path, tier="auto_send", max_profiles=None, only_new=True
            )
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(len(approved), 1)
        self.assertIn("fresh-lead", approved[0]["profile_url"])


class TestOllamaRetryAndCircuit(unittest.TestCase):
    def setUp(self) -> None:
        reset_circuit_breaker()
        self.cfg = {
            "llm": {
                "enabled": True,
                "retry_enabled": True,
                "circuit_breaker_threshold": 3,
                "agents": {"discovery": {"enabled": True}},
            }
        }

    def tearDown(self) -> None:
        reset_circuit_breaker()

    def test_invoke_with_retry_succeeds_on_second_attempt(self) -> None:
        calls = {"n": 0}

        def flaky() -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("read timed out")
            return "ok"

        result = _invoke_with_retry(flaky, full_cfg=self.cfg)
        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 2)

    def test_circuit_breaker_disables_agents_after_three_fails(self) -> None:
        def always_fail() -> None:
            raise TimeoutError("read timed out")

        for _ in range(3):
            with self.assertRaises(TimeoutError):
                _invoke_with_retry(always_fail, full_cfg=self.cfg)
        self.assertFalse(agent_enabled(self.cfg, "discovery"))

    def test_parse_errors_do_not_trip_circuit_breaker(self) -> None:
        def parse_fail() -> None:
            raise ValueError("Invalid json output")

        for _ in range(5):
            with self.assertRaises(ValueError):
                _invoke_with_retry(parse_fail, full_cfg=self.cfg)
        self.assertTrue(agent_enabled(self.cfg, "discovery"))


class TestPersonaStats(unittest.TestCase):
    def test_persona_stats_aggregator_counts_correctly(self) -> None:
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        )
        path = Path(tmp.name)
        writer = csv.DictWriter(
            tmp,
            fieldnames=["profile_url", "status", "persona", "accepted_at", "reply_at"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "profile_url": "https://www.linkedin.com/in/a/",
                "status": "sent",
                "persona": "retail_area_leader",
                "accepted_at": "2026-01-01",
                "reply_at": "",
            }
        )
        writer.writerow(
            {
                "profile_url": "https://www.linkedin.com/in/b/",
                "status": "sent",
                "persona": "retail_area_leader",
                "accepted_at": "",
                "reply_at": "",
            }
        )
        tmp.close()
        try:
            stats = aggregate_persona_stats(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(stats["retail_area_leader"]["sent"], 2)
        self.assertEqual(stats["retail_area_leader"]["accepted"], 1)
        self.assertAlmostEqual(stats["retail_area_leader"]["rate"], 0.5)

    def test_persona_boost_factor_clamped(self) -> None:
        stats = {"retail_area_leader": {"sent": 10, "accepted": 8, "rate": 0.8}}
        factor = persona_boost_factor("retail_area_leader", stats)
        self.assertAlmostEqual(factor, 1.18)
        self.assertLessEqual(factor, 1.3)
        self.assertGreaterEqual(factor, 0.7)

    @patch.object(hn, "_load_full_linkedin_cfg")
    def test_rank_candidate_applies_persona_boost_when_stats_present(
        self, mock_cfg: MagicMock
    ) -> None:
        mock_cfg.return_value = {"automation": {"use_persona_stats": True}}
        candidate = hn.ProfileCandidate(
            profile_url="https://www.linkedin.com/in/lina-area/",
            name="Lina Area",
            headline="Area Manager premium retail Lithuania",
            company="Premium Fashion Baltics",
            location="Vilnius, Lithuania",
        )
        persona = hn.classify_persona(candidate, hn.default_hiring_network_config())
        cv = hn.match_candidate_to_cv(candidate, hn.default_hiring_network_config())
        history = hn.HistorySignals(sent_count=10, accepted_count=8)
        cfg = hn.default_hiring_network_config()
        with patch("recruiter_persona_stats.load_persona_stats") as mock_stats:
            mock_stats.return_value = {
                persona.persona: {"sent": 10, "accepted": 8, "rate": 0.8}
            }
            boosted = hn.rank_candidate(candidate, persona, cv, cfg, history)
        reset = hn.rank_candidate(
            candidate,
            persona,
            cv,
            cfg,
            hn.HistorySignals(sent_count=0, accepted_count=0),
        )
        with patch.object(
            hn,
            "_load_full_linkedin_cfg",
            return_value={"automation": {"use_persona_stats": False}},
        ):
            baseline = hn.rank_candidate(candidate, persona, cv, cfg, history)
        self.assertGreaterEqual(boosted, baseline)

    @patch.object(hn, "_load_full_linkedin_cfg")
    def test_rank_candidate_unaffected_when_stats_missing(
        self, mock_cfg: MagicMock
    ) -> None:
        mock_cfg.return_value = {"automation": {"use_persona_stats": True}}
        candidate = hn.ProfileCandidate(
            profile_url="https://www.linkedin.com/in/lina-area/",
            name="Lina Area",
            headline="Area Manager premium retail Lithuania",
            company="Premium Fashion Baltics",
            location="Vilnius, Lithuania",
        )
        persona = hn.classify_persona(candidate, hn.default_hiring_network_config())
        cv = hn.match_candidate_to_cv(candidate, hn.default_hiring_network_config())
        history = hn.HistorySignals()
        cfg = hn.default_hiring_network_config()
        with patch("recruiter_persona_stats.load_persona_stats", return_value={}):
            score_a = hn.rank_candidate(candidate, persona, cv, cfg, history)
            score_b = hn.rank_candidate(candidate, persona, cv, cfg, history)
        self.assertEqual(score_a, score_b)


class TestWritePersonaStats(unittest.TestCase):
    def test_write_persona_stats_creates_json(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        csv_path = Path(tmp.name) / "recruiters.csv"
        out_path = Path(tmp.name) / "persona_stats.json"
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "profile_url",
                    "status",
                    "persona",
                    "accepted_at",
                    "reply_at",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "profile_url": "https://www.linkedin.com/in/x/",
                    "status": "sent",
                    "persona": "hiring_manager",
                    "accepted_at": "2026-01-02",
                    "reply_at": "",
                }
            )
        stats = write_persona_stats(output_path=out_path, csv_path=csv_path)
        self.assertTrue(out_path.is_file())
        self.assertIn("hiring_manager", stats)


class TestWebDiscoverParsing(unittest.TestCase):
    def test_guess_location_from_exa_snippet(self) -> None:
        from recruiter_web_discover import guess_location_from_snippet

        snippet = (
            "Head Of Physical Retail at [Dyson](https://www.linkedin.com/company/dyson)\n\n"
            "Boston, Massachusetts, United States (US)\n\n500 connections"
        )
        self.assertIn("Boston", guess_location_from_snippet(snippet))

        lt_snippet = (
            "Head Of Private Label at [Maxima](https://linkedin.com/company/maxima)\n\n"
            "Vilnius, Lithuania\n\n500 connections"
        )
        self.assertIn("Vilnius", guess_location_from_snippet(lt_snippet))

        exp_snippet = (
            "Head Of Private Label at [Maxima](https://linkedin.com/company/maxima)\n\n"
            "500 connections\n\n"
            "### Role at Maxima (Current)\n\n"
            "Sep 2019 - Present (6 years) in Vilniaus, Lithuania\n"
        )
        self.assertIn("Vilnius", guess_location_from_snippet(exp_snippet))

    def test_guess_company_from_exa_snippet(self) -> None:
        from recruiter_web_discover import guess_company_from_hit
        from recruiter_web_research import WebSearchHit

        hit = WebSearchHit(
            title="Iuliia Kliuchkovska - Head of Physical Retail at Dyson - LinkedIn",
            url="https://www.linkedin.com/in/iuliia-kliuchkovska-17820432/",
            snippet=(
                "Head Of Physical Retail at [Dyson](https://www.linkedin.com/company/dyson)\n"
                "Boston, Massachusetts, United States (US)"
            ),
            source="web_exa",
        )
        self.assertEqual(guess_company_from_hit(hit), "Dyson")

    def test_generic_llm_location_does_not_override_snippet(self) -> None:
        from recruiter_ollama_agents import DiscoveryExtraction
        from recruiter_web_discover import _merge_llm_extraction

        extraction = DiscoveryExtraction(
            name="",
            headline="",
            company="",
            profile_url="",
            location="Lithuania",
            discovery_notes="",
        )
        _, _, _, _, location, _ = _merge_llm_extraction(
            name="Test",
            headline="",
            company="",
            profile_url="https://www.linkedin.com/in/test/",
            location="Boston, Massachusetts, United States (US)",
            discovery_notes="",
            extraction=extraction,
        )
        self.assertIn("Boston", location)


class TestVilniusGeoFilter(unittest.TestCase):
    def test_passes_vilnius_scope(self) -> None:
        from recruiter_web_discover import passes_geo_filter

        self.assertTrue(
            passes_geo_filter(
                "Vilnius, Lithuania",
                "Head of retail at Apranga",
                scope="vilnius",
            )
        )
        self.assertFalse(
            passes_geo_filter(
                "Boston, Massachusetts, United States (US)",
                "Michael Kors luxury retail",
                scope="vilnius",
            )
        )

    def test_passes_europe_scope(self) -> None:
        from recruiter_web_discover import passes_geo_filter

        self.assertTrue(
            passes_geo_filter(
                "London, United Kingdom",
                "Hiring luxury retail leaders across Europe",
                scope="europe",
            )
        )
        self.assertTrue(
            passes_geo_filter(
                "",
                "Remote Europe service delivery manager hiring",
                scope="europe",
            )
        )
        self.assertFalse(
            passes_geo_filter(
                "Las Vegas Metropolitan Area (US)",
                "Michael Kors luxury retail",
                scope="europe",
            )
        )

    def test_hit_to_discovery_row_skips_abroad_when_geo_required(self) -> None:
        from recruiter_web_discover import hit_to_discovery_row
        from recruiter_web_research import WebSearchHit

        full_cfg = {
            "web_discovery": {"geo_scope": "vilnius", "require_geo_match": True},
            "llm": {"enabled": False},
            "hiring_network": hn.default_hiring_network_config(),
            "matching": {"min_primary_score": 8},
        }
        hit = WebSearchHit(
            title="Nicole H Han - Michael Kors - LinkedIn",
            url="https://www.linkedin.com/in/nicole-h-han-0b102b138/",
            snippet="Store Manager at Michael Kors\nLas Vegas Metropolitan Area (US)",
            source="web_exa",
        )
        row = hit_to_discovery_row(
            hit,
            variant_slug="luxury-retail",
            hn_cfg=hn.default_hiring_network_config(),
            full_cfg=full_cfg,
            seen_urls=set(),
            backend="web_exa",
        )
        self.assertIsNone(row)


class TestValidationRankBoost(unittest.TestCase):
    def test_approved_boost_increases_score(self) -> None:
        from hiring_network_workflow import (
            PersonaDecision,
            apply_validation_rank_adjustments,
        )

        persona = PersonaDecision(
            persona="recruiter_hr",
            hiring_authority_score=80,
            confidence=0.8,
            evidence=["talent acquisition"],
            risk_flags=[],
        )
        score, softened = apply_validation_rank_adjustments(
            52.0,
            validation_status="approved",
            company_relevance_score=72.0,
            persona=persona,
        )
        self.assertGreaterEqual(score, 60.0)
        self.assertIn("no_hiring_network_signal", softened)

    def test_clear_fresh_run_artifacts(self) -> None:
        from recruiter_linkedin_paths import (
            ACTION_PLAN_JSONL,
            clear_fresh_run_artifacts,
        )

        ACTION_PLAN_JSONL.parent.mkdir(parents=True, exist_ok=True)
        ACTION_PLAN_JSONL.write_text('{"old": true}\n', encoding="utf-8")
        clear_fresh_run_artifacts()
        self.assertEqual(ACTION_PLAN_JSONL.read_text(encoding="utf-8"), "")


class TestResolvePersona(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = hn.load_workflow_config(
            Path(__file__).resolve().parents[1] / "linkedin" / "config.yaml"
        )

    def test_preserves_discovery_hr_when_rank_classifier_drops(self) -> None:
        candidate = hn.ProfileCandidate(
            profile_url="https://www.linkedin.com/in/tatyanagorelova/",
            name="Tatyana Gorelova",
            headline="Programs Manager at Softeq",
            company="Softeq",
            location="Vilnius, Lithuania",
            scraped_text=(
                "Softeq is a full-stack development company. "
                "Our software and hardware engineers know how to program."
            ),
        )
        self.assertEqual(
            hn.classify_persona(candidate, self.cfg).persona, "low_relevance"
        )
        resolved = hn.resolve_persona(
            candidate,
            self.cfg,
            discovery_persona="recruiter_hr",
            validation_status="review",
            company_flags="",
        )
        self.assertEqual(resolved.persona, "recruiter_hr")
        self.assertIn(hn._DISCOVERY_PERSONA_PRESERVED, resolved.evidence)

    def test_staffing_flags_block_persona_preserve(self) -> None:
        candidate = hn.ProfileCandidate(
            profile_url="https://www.linkedin.com/in/spark/",
            name="Staff Lead",
            headline="Founder",
            company="Spark lab",
            location="Vilnius, Lithuania",
            scraped_text="Staffing agency recruitment",
        )
        resolved = hn.resolve_persona(
            candidate,
            self.cfg,
            discovery_persona="recruiter_hr",
            validation_status="review",
            company_flags="staffing_only",
        )
        self.assertEqual(resolved.persona, "low_relevance")

    def test_preserved_hr_gets_queue_review_not_skip(self) -> None:
        candidate = hn.ProfileCandidate(
            profile_url="https://www.linkedin.com/in/tatyanagorelova/",
            name="Tatyana Gorelova",
            headline="Talent Acquisition Manager at Softeq",
            company="Softeq",
            location="Vilnius, Lithuania",
            scraped_text=(
                "Talent acquisition manager hiring retail and operations leaders "
                "in Vilnius Lithuania."
            ),
        )
        invite = hn.build_ranked_invite(
            candidate,
            cfg=self.cfg,
            history=hn.HistorySignals(),
            already_contacted=False,
            pending_visible=False,
            validation_status="review",
            company_relevance_score=40.0,
            discovery_persona="recruiter_hr",
            company_flags="",
        )
        self.assertEqual(invite.persona.persona, "recruiter_hr")
        self.assertNotEqual(invite.send_tier, "skip")
        self.assertIn(invite.send_tier, {"queue_review", "auto_send"})


if __name__ == "__main__":
    unittest.main()
