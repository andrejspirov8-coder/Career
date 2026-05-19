"""Unit tests for LinkedIn recruiter helper modules (offline; no LinkedIn hits)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import linkedin_selectors as lis  # noqa: E402
import linkedin_recruiter_bot as bot  # noqa: E402
import recruiter_log as rlog  # noqa: E402
import recruiter_match as rm  # noqa: E402
import recruiter_orchestrate as orch  # noqa: E402


class TestCanonicalProfileUrls(unittest.TestCase):
    def test_strips_tracking_params(self) -> None:
        raw = (
            "https://www.linkedin.com/in/jane-example-123456?utm_source=blah"
            "&miniProfileUrn=x"
        )
        self.assertEqual(
            lis.canonical_profile_url(raw),
            "https://www.linkedin.com/in/jane-example-123456/",
        )


    def test_rejects_company_placeholder(self) -> None:
        self.assertEqual(lis.canonical_profile_url("https://www.linkedin.com/company/acme/in/bad"), "")


class TestBrowserChannelResolution(unittest.TestCase):
    def test_defaults_to_chrome(self) -> None:
        self.assertEqual(bot.resolve_browser_channel({}, None), "chrome")

    def test_chromium_alias_is_bundled(self) -> None:
        self.assertIsNone(bot.resolve_browser_channel({"browser": {"channel": "chromium"}}, None))

    def test_cli_override_wins(self) -> None:
        self.assertEqual(
            bot.resolve_browser_channel({"browser": {"channel": "chrome"}}, "chromium"),
            None,
        )


class TestPlannedInviteMetadata(unittest.TestCase):
    def test_planned_invite_lookup_uses_canonical_profile_url(self) -> None:
        planned = {
            "https://www.linkedin.com/in/jane-sample/": {
                "note": "Hi Jane, personalized note.",
                "persona": "retail_area_leader",
                "rank_score": 88.5,
                "safety_decision": "approved",
                "note_reason": "retail_area_leader:area manager:luxury-retail",
            }
        }
        found = bot.planned_invite_for_url(
            planned,
            "https://www.linkedin.com/in/jane-sample/?miniProfileUrn=abc",
        )
        self.assertIsNotNone(found)
        self.assertEqual(found.get("persona"), "retail_area_leader")

    def test_recruiter_log_schema_has_agentic_fields(self) -> None:
        row = rlog.recruiter_row_partial(
            persona="retail_area_leader",
            rank_score="88.5",
            profile_confidence="0.9",
            safety_decision="approved",
            note_reason="ranked",
            final_note="Hi Jane, personalized note.",
        )
        self.assertEqual(row["persona"], "retail_area_leader")
        self.assertEqual(row["rank_score"], "88.5")
        self.assertEqual(row["final_note"], "Hi Jane, personalized note.")


class TestBlockingHeuristics(unittest.TestCase):

    def test_checkpoint_url_detected(self) -> None:


        blocker = lis.detect_blockers(
            url="https://www.linkedin.com/checkpoint/lg/sign-in-phone",
            html_sample="<html></html>",
        )


        self.assertEqual(blocker, "checkpoint_or_auth_url")


class TestRecruiterMatchIntegration(unittest.TestCase):

    def test_explicit_retail_voice_scores_luxury(self) -> None:
        snippet = """

        Boutique talent partner hiring store managers across Baltics.


        Keywords: luxury retail, premium fashion, KPI, clienteling.


        Vilnius recruiter opening.

        """

        result = rm.match_recruiter_profile(
            headline="Senior recruiter – premium retail",
            name="Taylor Recruit",
            profile_url="https://www.linkedin.com/in/sample-recruiter/",
            company="TalentCo",
            about=snippet.strip(),
            role_text="Placed deputy managers across EU malls.",
            location="Vilnius, Lithuania",
            recruiter_cfg={},
        )

        ok, refusal = rm.should_send_recruiter_connection(
            result,
            min_primary_score=0.1,
            min_margin_over_second=0.0,
            require_clear_winner=False,
            require_recruiter_gate=False,
        )


        slug = result["recommendation"]["variant_slug"]

        self.assertTrue(ok)


        self.assertEqual(refusal, "")


        self.assertIn(slug, {"luxury-retail", "luxury-retail-lt", "operations-management"})
        self.assertGreater(result["recommendation"]["primary_score"], 8.0)

    def test_area_manager_passes_hiring_gate(self) -> None:
        result = rm.match_recruiter_profile(
            headline="Area Manager @ Premium Retail Group",
            name="Alex Ops",
            profile_url="https://www.linkedin.com/in/alex-ops/",
            company="Premium Retail Group",
            about="Leading 12 stores across Lithuania. Hiring store managers and deputy managers.",
            role_text="",
            location="Vilnius, Lithuania",
            recruiter_cfg={},
        )
        meta = result["recruiter_meta"]
        self.assertTrue(meta["recruiter_gate_ok"])
        self.assertFalse(meta["sales_only_no_hiring"])
        ok, refusal = rm.should_send_recruiter_connection(
            result,
            min_primary_score=0.1,
            min_margin_over_second=0.0,
            require_clear_winner=False,
            require_recruiter_gate=True,
        )
        self.assertTrue(ok, refusal)

    def test_pure_sales_blocked_without_hiring_signal(self) -> None:
        result = rm.match_recruiter_profile(
            headline="Account Executive | B2B SaaS",
            name="Sam Sales",
            profile_url="https://www.linkedin.com/in/sam-sales/",
            company="SaaSCo",
            about="Quota-carrying inside sales and pipeline generation.",
            role_text="",
            location="Remote",
            recruiter_cfg={},
        )
        meta = result["recruiter_meta"]
        self.assertFalse(meta["recruiter_gate_ok"])
        self.assertTrue(meta["sales_only_no_hiring"])
        ok, refusal = rm.should_send_recruiter_connection(
            result,
            min_primary_score=0.1,
            min_margin_over_second=0.0,
            require_clear_winner=False,
            require_recruiter_gate=True,
        )
        self.assertFalse(ok)
        self.assertEqual(refusal, "skipped_sales_only_no_hiring_signal")

    def test_assign_best_tier_respects_company_signals(self) -> None:
        scoring = {
            "recommendation": {
                "variant_slug": "luxury-retail",
                "primary_score": 16.0,
                "margin_over_second": 5.0,
                "confidence": "clear_winner",
            },
            "recruiter_meta": {"recruiter_gate_ok": True},
        }
        cfg = {
            "matching": {
                "min_primary_score": 12.0,
                "min_margin_over_second": 4.0,
                "require_recruiter_gate": True,
                "require_clear_winner": False,
                "note_max_chars": 280,
            },
            "tiers": {
                "tier_1": {
                    "min_primary_score": 15,
                    "min_margin_over_second": 4.0,
                    "require_recruiter_gate": True,
                    "require_clear_winner": True,
                    "allow_tie_review": False,
                    "company_signals_any": ["michael page"],
                },
                "tier_2": {
                    "min_primary_score": 12,
                    "company_signals_any": [],
                },
            },
        }
        tk, refusal = rm.assign_best_tier(
            result=scoring,
            cfg=cfg,
            company_blob_lower="we work at michael page europe",
        )
        self.assertEqual(tk, "tier_1")
        self.assertEqual(refusal, "")

        tk2, _ = rm.assign_best_tier(
            result=scoring,
            cfg=cfg,
            company_blob_lower="generic boutique vilnius recruiter",
        )
        self.assertEqual(tk2, "tier_2")


class TestOrchestratorLatestJsonl(unittest.TestCase):
    def test_latest_record_wins_duplicate_url(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
            p = Path(tmp.name)
            tmp.write(
                '{"profile_url":"https://www.linkedin.com/in/jane-sample/","tier":"tier_2"}\n'
            )
            tmp.write(
                '{"profile_url":"https://www.linkedin.com/in/jane-sample/","tier":"tier_1"}\n'
            )

        try:
            m = orch.read_jsonl_latest_by_url(p)
        finally:
            p.unlink(missing_ok=True)

        canon = lis.canonical_profile_url("https://www.linkedin.com/in/jane-sample/")
        self.assertIsNotNone(canon)
        self.assertEqual(m.get(canon or "")["tier"], "tier_1")

    def test_prepare_outreach_note_keyword_suffix(self) -> None:
        res = rm.match_profile(
            headline="recruiter",
            name="Pat Example",
            profile_url="https://www.linkedin.com/in/pat/",
            company="StaffCo",
            about="We hire luxury retail boutique managers.",
            role_text="Retail hiring across Baltics.",
            location="Vilnius",
        )
        out = rm.prepare_outreach_note(
            match_result=res,
            headline="recruiter",
            about="We hire luxury retail boutique managers.",
            location_txt="Vilnius",
            display_name="Pat Example",
            search_variant_slug="luxury-retail",
            meta_signals_csv="luxury,premium retail",
            note_templates_raw={
                "luxury-retail": "Hi {first_name}, boutique retail Vilnius ping.",
            },
            matching_cfg={
                "append_top_keyword_hit_to_note_if_fits_chars": True,
                "note_max_chars": 280,
            },
        )
        note = out.get("note_live_full") or ""
        self.assertIn("luxury", note.lower())
        self.assertLessEqual(len(note), 280)
