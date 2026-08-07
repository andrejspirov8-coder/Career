"""Unit tests for LinkedIn recruiter helper modules (offline; no LinkedIn hits)."""

from __future__ import annotations

import unittest
from pathlib import Path

from career_job_search.integrations.linkedin import campaign as bot
from career_job_search.integrations.linkedin import selectors as lis
from career_job_search.recruiters import log as rlog
from career_job_search.recruiters import matching as rm
from career_job_search.recruiters import orchestrator as orch


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
        self.assertEqual(
            lis.canonical_profile_url("https://www.linkedin.com/company/acme/in/bad"),
            "",
        )

    def test_normalizes_to_www_for_no_subdomain_input(self) -> None:
        """Exa returns URLs like 'linkedin.com/in/foo' (no www) — we must
        canonicalize those identically to 'https://www.linkedin.com/in/foo/'
        so the enrichment dict-lookup succeeds."""
        canon_no_www = lis.canonical_profile_url("linkedin.com/in/tatyanagorelova")
        canon_with_www = lis.canonical_profile_url(
            "https://www.linkedin.com/in/tatyanagorelova/"
        )
        self.assertEqual(canon_no_www, canon_with_www)
        self.assertEqual(canon_no_www, "https://www.linkedin.com/in/tatyanagorelova/")


class TestBrowserChannelResolution(unittest.TestCase):
    def test_defaults_to_chrome(self) -> None:
        self.assertEqual(bot.resolve_browser_channel({}, None), "chrome")

    def test_chromium_alias_is_bundled(self) -> None:
        self.assertIsNone(
            bot.resolve_browser_channel({"browser": {"channel": "chromium"}}, None)
        )

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

        self.assertIn(
            slug, {"luxury-retail", "luxury-retail-lt", "operations-management"}
        )
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

        with tempfile.NamedTemporaryFile(
            "w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as tmp:
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

    def test_daily_dry_run_defaults_to_bounded_scout_cap(self) -> None:
        self.assertEqual(
            orch.default_daily_scout_cap(
                dry_run=True,
                max_dispatch=1,
                max_scout=None,
            ),
            1,
        )
        self.assertEqual(
            orch.default_daily_scout_cap(
                dry_run=True,
                max_dispatch=None,
                max_scout=None,
            ),
            5,
        )
        self.assertIsNone(
            orch.default_daily_scout_cap(
                dry_run=False,
                max_dispatch=1,
                max_scout=None,
            )
        )

    def test_campaign_config_overrides_do_not_mutate_source(self) -> None:
        source = {
            "limits": {
                "max_profiles_scored_per_run": 75,
                "dwell_after_navigate_seconds_max": 6,
            }
        }

        bounded = orch.campaign_config_with_overrides(
            source,
            max_profiles_scored=2,
            login_timeout_seconds=15,
            fast_dry_run=True,
        )

        self.assertEqual(source["limits"]["max_profiles_scored_per_run"], 75)
        self.assertEqual(bounded["limits"]["max_profiles_scored_per_run"], 2)
        self.assertEqual(bounded["limits"]["login_timeout_seconds"], 15)
        self.assertLessEqual(bounded["limits"]["dwell_after_navigate_seconds_max"], 2)

    def test_dry_run_dispatch_empty_queue_is_clean_noop(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cfg = root / "config.yaml"
            cfg.write_text("limits: {}\n", encoding="utf-8")
            session = root / "session.json"
            session.write_text(
                '{"schema":"recruiter_session_state_v1","queue":[]}\n',
                encoding="utf-8",
            )

            rc = orch.cmd_dispatch(
                cfg_path=cfg,
                headed=False,
                dry_run=True,
                browser_channel=None,
                tier_filter=None,
                max_profiles=1,
                session_path=session,
            )

        self.assertEqual(rc, 0)

    def test_live_dispatch_rejects_missing_or_oversized_max_before_file_access(
        self,
    ) -> None:
        for value, message in ((None, "explicit --max"), (4, "cannot exceed 3")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(SystemExit, message):
                    orch.cmd_dispatch(
                        cfg_path=Path("/definitely/missing/config.yaml"),
                        headed=False,
                        dry_run=False,
                        browser_channel=None,
                        tier_filter=None,
                        max_profiles=value,
                        session_path=Path("/definitely/missing/session.json"),
                        allow_live_dispatch=True,
                    )

    def test_three_logged_sends_leave_zero_budget_for_a_later_run(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            csv_path = root / "recruiters.csv"
            state_db = root / "state.sqlite3"
            for index in range(3):
                rlog.append_recruiter_row(
                    rlog.recruiter_row_partial(
                        date_iso=bot.date.today().isoformat(),
                        profile_url=f"https://www.linkedin.com/in/sent-{index}/",
                        status="sent",
                    ),
                    csv_path=csv_path,
                )

            sent = bot.successful_sends_today(csv_path, state_db=state_db)

        self.assertEqual(sent, 3)
        self.assertEqual(
            bot.live_dispatch_slots_remaining(sent, requested_max=3),
            0,
        )
        self.assertEqual(
            bot.effective_daily_invite_cap(
                {
                    "max_connections_per_day": 50,
                    "max_connections_per_day_low_accept": 50,
                },
                csv_path=Path("/definitely/missing/recruiters.csv"),
            ),
            3,
        )

    def test_hiring_network_daily_forwards_live_dispatch_acknowledgement(self) -> None:
        calls: list[list[str]] = []
        original_call = orch.subprocess.call

        def fake_call(cli: list[str]) -> int:
            calls.append(cli)
            return 0

        try:
            orch.subprocess.call = fake_call
            rc = orch.main(
                [
                    "daily",
                    "--mode",
                    "hiring_network",
                    "--no-headed",
                    "--max-dispatch",
                    "2",
                    "--allow-live-dispatch",
                ]
            )
        finally:
            orch.subprocess.call = original_call

        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("--auto-send", calls[0])
        self.assertIn("--allow-live-dispatch", calls[0])

    def test_daily_live_mode_rejects_missing_max_before_scout_browser(self) -> None:
        original_scout = orch.cmd_scout

        def fail_if_scouted(**_kwargs: object) -> int:
            raise AssertionError("browser-backed scout must not start")

        try:
            orch.cmd_scout = fail_if_scouted  # type: ignore[assignment]
            with self.assertRaisesRegex(SystemExit, "explicit --max-dispatch"):
                orch.main(["daily", "--no-headed"])
        finally:
            orch.cmd_scout = original_scout

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
