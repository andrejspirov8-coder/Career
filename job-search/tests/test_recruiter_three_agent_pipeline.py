"""Tests for three-agent discovery CSV pipeline."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import hiring_network_workflow as hn  # noqa: E402
import recruiter_company_validate as rcv  # noqa: E402
import recruiter_discovery_csv as rdc  # noqa: E402
from recruiter_discovery_bridge import (  # noqa: E402
    rows_for_bridge,
    validated_to_scout_records,
)
from recruiter_web_discover import run_discovery  # noqa: E402
from recruiter_web_research import OfflineStubBackend  # noqa: E402


class TestDiscoveryCsv(unittest.TestCase):
    def test_write_and_read_discovery_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "discovery.csv"
            rows = [
                rdc.discovery_row_partial(
                    profile_url="https://www.linkedin.com/in/jane-retail/",
                    name="Jane Retail",
                    headline="Area Manager premium retail",
                    company="Apranga",
                    rank_score_draft="82.5",
                )
            ]
            rdc.write_discovery_rows(rows, path)
            loaded = rdc.read_discovery_rows(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["name"], "Jane Retail")

    def test_validated_extends_discovery(self) -> None:
        base = rdc.discovery_row_partial(name="Test")
        validated = rdc.discovery_to_validated(base)
        self.assertIn("validation_status", validated)
        self.assertEqual(validated["name"], "Test")


class TestBridge(unittest.TestCase):
    def test_rows_for_bridge_filters_reject(self) -> None:
        rows = [
            rdc.validated_row_partial(
                profile_url="https://www.linkedin.com/in/ok/",
                validation_status="approved",
            ),
            rdc.validated_row_partial(
                profile_url="https://www.linkedin.com/in/nope/",
                validation_status="reject",
            ),
        ]
        bridged = rows_for_bridge(rows)
        self.assertEqual(len(bridged), 1)

    def test_validated_to_scout_record_shape(self) -> None:
        row = rdc.validated_row_partial(
            profile_url="https://www.linkedin.com/in/lina-area/",
            name="Lina Area",
            headline="Area Manager premium retail Lithuania",
            company="Premium Fashion Baltics",
            location="Vilnius, Lithuania",
            variant_slug="luxury-retail",
            validation_status="approved",
        )
        cfg = hn.default_hiring_network_config()
        full_cfg = {"hiring_network": cfg, "matching": {"min_primary_score": 8}}
        row["persona"] = "recruiter_hr"
        row["discovery_notes"] = "# Tatyana Gorelova\nTalent Acquisition Manager"
        records = validated_to_scout_records([row], cfg=full_cfg)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["schema"], "linkedin_recruit_scout_v1")
        self.assertEqual(records[0].get("discovery_persona"), "recruiter_hr")
        self.assertIn("Tatyana", str(records[0].get("discovery_persona_evidence")))


class TestCompanyValidate(unittest.TestCase):
    def test_approve_track_aligned_company(self) -> None:
        hn_cfg = hn.load_workflow_config(
            Path(__file__).resolve().parents[1] / "linkedin" / "config.yaml"
        )
        score, flags, rationale = rcv.score_company_from_text(
            "Apranga Group",
            "Premium luxury fashion retail group in Vilnius Lithuania Baltics",
            hn_cfg=hn_cfg,
            cv_cfg={},
        )
        self.assertGreaterEqual(score, 60)
        self.assertTrue(rationale)

    def test_reject_staffing_company(self) -> None:
        hn.default_hiring_network_config()
        status = rcv.validation_status_for_row(
            sector_score=30,
            flags=["staffing_only"],
            needs_linkedin_url=False,
            approve_threshold=60,
            review_threshold=40,
        )
        self.assertEqual(status, "reject")

    def test_hr_persona_lifts_off_sector_company_into_review(self) -> None:
        """HR recruiters at non-retail Vilnius companies must not be rejected
        for "weak sector alignment" — they hire across sectors."""
        hn_cfg = hn.load_workflow_config(
            Path(__file__).resolve().parents[1] / "linkedin" / "config.yaml"
        )
        cv_cfg = {"company_validation": {"persona_cross_sector_boost": 25}}
        baseline, _, _ = rcv.score_company_from_text(
            "Softeq",
            "Softeq is a software development company in Vilnius Lithuania",
            hn_cfg=hn_cfg,
            cv_cfg=cv_cfg,
            profile_location="Vilnius, Lithuania",
            persona="",
        )
        boosted, _, rationale = rcv.score_company_from_text(
            "Softeq",
            "Softeq is a software development company in Vilnius Lithuania",
            hn_cfg=hn_cfg,
            cv_cfg=cv_cfg,
            profile_location="Vilnius, Lithuania",
            persona="recruiter_hr",
        )
        self.assertGreater(boosted, baseline)
        self.assertGreaterEqual(boosted, 40.0, msg=f"rationale={rationale}")
        self.assertIn("boost", rationale.lower())

    def test_hr_persona_boost_suppressed_when_staffing_only(self) -> None:
        """The HR boost must not save staffing agencies — those are always
        rejected regardless of persona."""
        hn_cfg = hn.default_hiring_network_config()
        cv_cfg = {"company_validation": {"persona_cross_sector_boost": 25}}
        score, flags, rationale = rcv.score_company_from_text(
            "Spark Lab",
            "Spark Lab is a staffing agency in Vilnius Lithuania",
            hn_cfg=hn_cfg,
            cv_cfg=cv_cfg,
            profile_location="Vilnius, Lithuania",
            persona="recruiter_hr",
        )
        self.assertIn("staffing_only", flags)
        self.assertNotIn("boost", rationale.lower())
        # Score must stay low enough to be hard-rejected by status logic.
        status = rcv.validation_status_for_row(
            sector_score=score,
            flags=flags,
            needs_linkedin_url=False,
            approve_threshold=60,
            review_threshold=40,
        )
        self.assertEqual(status, "reject")


class TestWebDiscoverOffline(unittest.TestCase):
    def test_offline_discovery_writes_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.yaml"
            out_path = Path(tmp) / "discovery.csv"
            cfg_path.write_text(
                json.dumps(
                    {
                        "web_discovery": {
                            "backend": "offline",
                            "queries_by_variant": {
                                "luxury-retail": ["luxury retail Vilnius"]
                            },
                        },
                        "hiring_network": hn.default_hiring_network_config(),
                        "matching": {"min_primary_score": 8},
                    }
                ),
                encoding="utf-8",
            )

            # YAML loader needed — rewrite as yaml
            cfg_path.write_text(
                "web_discovery:\n"
                "  backend: offline\n"
                "  queries_by_variant:\n"
                "    luxury-retail:\n"
                "      - luxury retail Vilnius\n"
                "matching:\n"
                "  min_primary_score: 8\n",
                encoding="utf-8",
            )
            rows, _ = run_discovery(
                cfg_path=cfg_path,
                output_path=out_path,
                backend="offline",
                no_llm=True,
            )
            self.assertGreaterEqual(len(rows), 1)
            self.assertTrue(out_path.exists())

    def test_offline_backend_returns_linkedin_hits(self) -> None:
        backend = OfflineStubBackend()
        result = backend.search("luxury retail Vilnius")
        self.assertGreaterEqual(len(result.hits), 1)
        self.assertIn("linkedin.com/in/", result.hits[0].url.lower())


class TestLangGraphBuild(unittest.TestCase):
    def test_build_langgraph_workflow_compiles(self) -> None:
        try:
            workflow = hn.build_langgraph_workflow("discovery")
        except RuntimeError as exc:
            if "LangGraph is not installed" in str(exc):
                self.skipTest("langgraph not installed")
            raise
        self.assertIsNotNone(workflow)


if __name__ == "__main__":
    unittest.main()
