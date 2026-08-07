"""Track-aware send gate tests."""

from __future__ import annotations

import unittest

from career_job_search.recruiters import matching as rm


class TestTrackRelevanceGate(unittest.TestCase):
    def test_staffing_agency_blocked_with_track_gate(self) -> None:
        cfg = {
            "matching": {
                "require_sector_and_cv_agreement": True,
                "cv_min_scores": {"luxury-retail": 8.0},
            },
            "recruiter_matching": {
                "outreach_exclude_terms": ["staffing agency"],
                "track_aligned_company_terms": ["luxury", "fashion", "retail"],
            },
        }
        result = rm.match_recruiter_profile(
            headline="Recruiter",
            name="Pat Staff",
            profile_url="https://www.linkedin.com/in/pat-staff/",
            company="Universal Staffing Agency",
            about="General recruitment for all sectors.",
            role_text="",
            location="Vilnius",
            recruiter_cfg=cfg,
        )
        ok, refusal = rm.should_send_recruiter_connection(
            result,
            min_primary_score=0.1,
            min_margin_over_second=0.0,
            require_clear_winner=False,
            require_recruiter_gate=False,
            full_cfg=cfg,
        )
        self.assertFalse(ok)
        self.assertIn("exclude", refusal)

    def test_premium_retail_passes_track_gate(self) -> None:
        cfg = {
            "matching": {
                "require_sector_and_cv_agreement": True,
                "cv_min_scores": {"luxury-retail": 8.0},
            },
            "recruiter_matching": {
                "track_aligned_company_terms": [
                    "luxury",
                    "premium",
                    "fashion",
                    "retail",
                ],
            },
        }
        result = rm.match_recruiter_profile(
            headline="Area Manager premium fashion",
            name="Lina Retail",
            profile_url="https://www.linkedin.com/in/lina-retail/",
            company="Michael Kors",
            about="Luxury retail leadership and hiring store managers.",
            role_text="",
            location="Vilnius, Lithuania",
            recruiter_cfg=cfg,
        )
        ok, refusal = rm.should_send_recruiter_connection(
            result,
            min_primary_score=0.1,
            min_margin_over_second=0.0,
            require_clear_winner=False,
            require_recruiter_gate=True,
            full_cfg=cfg,
        )
        self.assertTrue(ok, refusal)


if __name__ == "__main__":
    unittest.main()
