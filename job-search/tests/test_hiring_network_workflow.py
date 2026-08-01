"""Offline tests for the agentic hiring-network workflow.

These tests do not open LinkedIn. They validate the deterministic agent
contracts that sit before browser dispatch.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from career_job_search.recruiters import hiring_network as hn  # noqa: E402


class TestHiringNetworkSchemas(unittest.TestCase):
    def test_profile_candidate_rejects_non_linkedin_profile_url(self) -> None:
        with self.assertRaises(ValueError):
            hn.ProfileCandidate(
                profile_url="https://www.linkedin.com/company/acme/",
                name="Acme",
                headline="Company page",
            )

    def test_ranked_invite_rejects_overlong_note(self) -> None:
        candidate = hn.ProfileCandidate(
            profile_url="https://www.linkedin.com/in/jane-retail/",
            name="Jane Retail",
            headline="Area Manager premium retail Lithuania",
        )
        persona = hn.classify_persona(candidate, hn.default_hiring_network_config())
        cv_match = hn.match_candidate_to_cv(
            candidate, hn.default_hiring_network_config()
        )
        with self.assertRaises(ValueError):
            hn.RankedInvite(
                candidate=candidate,
                persona=persona,
                cv_match=cv_match,
                rank_score=91.0,
                send_tier="auto_send",
                note="x" * 281,
                risk_flags=[],
                decision="approved",
                note_reason="test",
            )


class TestHiringNetworkClassification(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = hn.default_hiring_network_config()

    def classify(
        self, headline: str, about: str = "", company: str = ""
    ) -> hn.PersonaDecision:
        candidate = hn.ProfileCandidate(
            profile_url="https://www.linkedin.com/in/sample-person/",
            name="Sample Person",
            headline=headline,
            company=company,
            scraped_text=about,
            location="Vilnius, Lithuania",
        )
        return hn.classify_persona(candidate, self.cfg)

    def test_area_manager_is_retail_area_leader(self) -> None:
        persona = self.classify(
            "Area Manager premium retail Baltics",
            "Hiring store managers and deputy managers across Lithuania.",
        )
        self.assertEqual(persona.persona, "retail_area_leader")
        self.assertGreaterEqual(persona.hiring_authority_score, 80)
        self.assertIn("area manager", [x.lower() for x in persona.evidence])

    def test_store_director_is_store_leader(self) -> None:
        persona = self.classify(
            "Store Director luxury fashion Vilnius",
            "Responsible for store teams, client experience, and hiring.",
        )
        self.assertEqual(persona.persona, "store_director")
        self.assertGreaterEqual(persona.confidence, 0.75)

    def test_it_support_manager_is_it_business_leader(self) -> None:
        persona = self.classify(
            "IT Support Manager",
            "Leading service desk hiring and business systems support in Lithuania.",
        )
        self.assertEqual(persona.persona, "it_business_leader")

    def test_pure_sales_profile_is_low_relevance(self) -> None:
        persona = self.classify(
            "Account Executive B2B SaaS",
            "Quota-carrying sales and outbound pipeline generation.",
        )
        self.assertEqual(persona.persona, "low_relevance")
        self.assertIn("sales_only_no_hiring_signal", persona.risk_flags)

    def test_generic_director_without_industry_is_low_relevance(self) -> None:
        persona = self.classify(
            "Director",
            "Corporate strategy and governance.",
            company="Generic Holdings",
        )
        self.assertEqual(persona.persona, "low_relevance")

    def test_finance_director_without_retail_is_not_area_leader(self) -> None:
        persona = self.classify(
            "Finance Director",
            "FP&A and treasury for a manufacturing group.",
            company="Industrial Group",
        )
        self.assertNotEqual(persona.persona, "retail_area_leader")


class TestHiringNetworkRankingAndNotes(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = hn.default_hiring_network_config()

    def candidate(self) -> hn.ProfileCandidate:
        return hn.ProfileCandidate(
            profile_url="https://www.linkedin.com/in/lina-area/",
            name="Lina Area",
            headline="Area Manager premium retail Lithuania",
            company="Premium Fashion Baltics",
            location="Vilnius, Lithuania",
            scraped_text="Hiring store managers and developing high-touch retail teams.",
        )

    def test_matching_selects_luxury_retail_for_premium_retail_profile(self) -> None:
        match = hn.match_candidate_to_cv(self.candidate(), self.cfg)
        self.assertIn(match.best_cv_variant, {"luxury-retail", "luxury-retail-lt"})
        self.assertGreater(match.score, 0)
        self.assertTrue(match.evidence)

    def test_ranked_invite_auto_sends_strong_profile(self) -> None:
        invite = hn.build_ranked_invite(
            self.candidate(),
            cfg=self.cfg,
            history=hn.HistorySignals(),
            already_contacted=False,
            pending_visible=False,
        )
        self.assertEqual(invite.send_tier, "auto_send")
        self.assertEqual(invite.decision, "approved")
        self.assertGreaterEqual(invite.rank_score, self.cfg["auto_send_threshold"])

    def test_note_is_personalized_and_under_limit(self) -> None:
        invite = hn.build_ranked_invite(
            self.candidate(),
            cfg=self.cfg,
            history=hn.HistorySignals(),
            already_contacted=False,
            pending_visible=False,
        )
        self.assertLessEqual(len(invite.note), 280)
        self.assertIn("Lina", invite.note)
        self.assertTrue(
            any(
                token in invite.note.lower()
                for token in ("retail", "vilnius", "lithuania")
            )
        )

    def test_search_variant_prior_approves_retail_hr_profile(self) -> None:
        candidate = hn.candidate_from_scout_record(
            {
                "profile_url": "https://www.linkedin.com/in/vitaval/",
                "name": "Vita Valiene",
                "headline": "HR Manager Apranga Group luxury retail Massimo Dutti",
                "variant_slug": "luxury-retail",
                "location": "Kaunas",
            }
        )
        invite = hn.build_ranked_invite(
            candidate,
            cfg=self.cfg,
            history=hn.HistorySignals(),
            already_contacted=False,
            pending_visible=False,
        )

        self.assertEqual(invite.cv_match.best_cv_variant, "luxury-retail")
        self.assertGreaterEqual(invite.cv_match.score, 76)
        self.assertEqual(invite.send_tier, "auto_send")
        self.assertIn("Apranga", invite.note)

    def test_action_record_includes_source_backend(self) -> None:
        candidate = hn.ProfileCandidate(
            profile_url="https://www.linkedin.com/in/lina-area/",
            name="Lina Area",
            headline="Area Manager premium retail Lithuania",
            source_backend="offline_stub",
        )
        invite = hn.build_ranked_invite(
            candidate,
            cfg=self.cfg,
            history=hn.HistorySignals(),
            already_contacted=False,
            pending_visible=False,
        )
        record = invite.to_action_record()
        self.assertEqual(record.get("source_backend"), "offline_stub")

    def test_safety_governor_skips_duplicates_and_pending_invites(self) -> None:
        duplicate = hn.build_ranked_invite(
            self.candidate(),
            cfg=self.cfg,
            history=hn.HistorySignals(),
            already_contacted=True,
            pending_visible=False,
        )
        self.assertEqual(duplicate.decision, "skip")
        self.assertIn("already_contacted", duplicate.risk_flags)

        pending = hn.build_ranked_invite(
            self.candidate(),
            cfg=self.cfg,
            history=hn.HistorySignals(),
            already_contacted=False,
            pending_visible=True,
        )
        self.assertEqual(pending.decision, "skip")
        self.assertIn("pending_invitation", pending.risk_flags)


class TestHiringNetworkFilesAndVision(unittest.TestCase):
    def test_action_plan_reader_accepts_json_array_legacy_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as tmp:
            path = Path(tmp.name)
            json.dump(
                [
                    {
                        "profile_url": "https://www.linkedin.com/in/jane/",
                        "name": "Jane",
                        "headline": "Recruiter",
                    }
                ],
                tmp,
            )

        try:
            rows = hn.read_action_plan_records(path)
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile_url"], "https://www.linkedin.com/in/jane/")

    def test_screen_state_labels_blocker_text(self) -> None:
        self.assertEqual(
            hn.classify_screen_state_from_text(
                "Please complete this CAPTCHA to continue"
            ),
            "captcha",
        )
        self.assertEqual(
            hn.classify_screen_state_from_text("Invite Lina Area to connect"),
            "connect_visible",
        )

    def test_legacy_recruiter_action_record_gets_recruiter_context(self) -> None:
        candidate = hn.candidate_from_scout_record(
            {
                "canonical_id": "recruiter:linkedin:jane-doe",
                "profile_url": "https://www.linkedin.com/in/jane-doe/",
                "recruiter_name": "Jane Doe",
                "company": "Michael Page Lithuania",
                "tier": "tier_1",
                "action": "send",
                "variant_slug": "luxury-retail",
            }
        )
        persona = hn.classify_persona(candidate, hn.default_hiring_network_config())
        self.assertEqual(persona.persona, "recruiter_hr")

    def test_full_auto_tier_includes_approved_auto_send(self) -> None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as tmp:
            path = Path(tmp.name)
            rows = [
                {
                    "profile_url": "https://www.linkedin.com/in/send-me/",
                    "name": "Send Me",
                    "headline": "Area Manager retail",
                    "decision": "approved",
                    "send_tier": "auto_send",
                    "cv_variant": "luxury-retail",
                },
                {
                    "profile_url": "https://www.linkedin.com/in/skip-me/",
                    "decision": "review",
                    "send_tier": "queue_review",
                    "cv_variant": "luxury-retail",
                },
            ]
            for row in rows:
                tmp.write(json.dumps(row) + "\n")

        try:
            approved = hn._approved_invites_from_plan(
                path, tier="full_auto", max_profiles=None
            )
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(len(approved), 1)
        self.assertIn("send-me", approved[0]["profile_url"])

    def test_dispatch_dry_run_previews_without_calling_browser_sender(self) -> None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as tmp:
            path = Path(tmp.name)
            tmp.write(
                json.dumps(
                    {
                        "profile_url": "https://www.linkedin.com/in/jane-dry-run/",
                        "name": "Jane Dry",
                        "send_tier": "auto_send",
                        "decision": "approved",
                        "cv_variant": "luxury-retail",
                        "rank_score": 88.0,
                        "persona": "retail_area_leader",
                        "note": "Hi Jane, dry-run note.",
                    }
                )
                + "\n"
            )

        class FailingBot:
            @staticmethod
            def load_config(config_path: Path) -> dict[str, object]:
                raise AssertionError("dry-run must not load sender config")

            @staticmethod
            def run_linked_in_campaign_backend(*args: object, **kwargs: object) -> int:
                raise AssertionError("dry-run must not call Playwright dispatcher")

        old_bot = hn.bot
        hn.bot = FailingBot()  # type: ignore[assignment]
        out = StringIO()
        try:
            with redirect_stdout(out):
                rc = hn.cmd_dispatch(
                    argparse.Namespace(
                        output=path,
                        tier="auto_send",
                        max=1,
                        dry_run=True,
                        headed=True,
                        config=hn.DEFAULT_LINKEDIN_CONFIG,
                        browser_channel=None,
                    )
                )
        finally:
            hn.bot = old_bot
            path.unlink(missing_ok=True)

        self.assertEqual(rc, 0)
        self.assertIn("DRY RUN", out.getvalue())
        self.assertIn("Jane Dry", out.getvalue())


if __name__ == "__main__":
    unittest.main()
