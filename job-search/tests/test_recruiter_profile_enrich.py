"""Tests for profile enrichment before rank."""

from __future__ import annotations

import unittest

from career_job_search.recruiters import hiring_network as hn
from career_job_search.recruiters.discovery_bridge import (
    validated_to_scout_records,
)
from career_job_search.recruiters.discovery_csv import (
    validated_row_partial,
)
from career_job_search.recruiters.profile_enrichment import (
    enrich_validated_rows,
    parse_exa_profile_text,
)


class TestProfileEnrichment(unittest.TestCase):
    def test_parse_exa_profile_text_extracts_about_and_role(self) -> None:
        text = (
            "# Lina HR\n\nTalent Acquisition Manager\n\n"
            "## About\n\nI hire retail leaders in Vilnius.\n\n"
            "## Experience\n\n### HR Manager at Apranga Group\nVilnius, Lithuania"
        )
        parsed = parse_exa_profile_text(text)
        self.assertIn("hire retail", parsed.about.lower())
        self.assertIn("Apranga", parsed.role_text)

    def test_offline_enrichment_updates_validated_csv(self) -> None:
        full_cfg = {
            "profile_enrichment": {
                "enabled": True,
                "backend": "offline",
                "only_statuses": ["approved"],
            },
            "hiring_network": hn.default_hiring_network_config(),
            "matching": {"min_primary_score": 8},
        }
        rows = [
            validated_row_partial(
                profile_url="https://www.linkedin.com/in/sample-retail-leader/",
                name="Sample Leader",
                validation_status="approved",
            )
        ]
        enriched, errors = enrich_validated_rows(
            rows, full_cfg=full_cfg, backend="offline"
        )
        self.assertFalse(errors)
        self.assertTrue((enriched[0].get("enriched_about") or "").strip())
        self.assertTrue((enriched[0].get("enriched_role_text") or "").strip())
        self.assertTrue((enriched[0].get("enriched_at") or "").strip())

    def test_bridge_passes_enriched_text_to_scout(self) -> None:
        row = validated_row_partial(
            profile_url="https://www.linkedin.com/in/sample-retail-leader/",
            name="Sample Leader",
            headline="Talent Acquisition Manager",
            company="Apranga Group",
            location="Vilnius, Lithuania",
            validation_status="approved",
            enriched_about="I lead hiring for premium retail in Vilnius.",
            enriched_role_text="HR Manager at Apranga Group",
        )
        cfg = {
            "hiring_network": hn.default_hiring_network_config(),
            "matching": {"min_primary_score": 8},
        }
        records = validated_to_scout_records([row], cfg=cfg)
        self.assertEqual(len(records), 1)
        self.assertIn("hiring", str(records[0].get("about")).lower())
        self.assertIn("Apranga", str(records[0].get("role_text")))

    def test_company_about_prefers_headline_for_role(self) -> None:
        from career_job_search.recruiters.profile_enrichment import (
            parse_exa_profile_text,
        )

        text = (
            "# Tatyana Gorelova\n\n"
            "Talent Acquisition Manager\n\n"
            "Emerging Talent Growth Manager at Softeq\n\n"
            "## About\n\n"
            "Softeq is a full-stack development company. Our software engineers build products.\n\n"
            "## Experience\n\n"
            "### Talent Acquisition Manager at Softeq\n"
        )
        parsed = parse_exa_profile_text(text)
        self.assertIn("Talent", parsed.role_text)
        self.assertNotIn("full-stack development", parsed.role_text.lower())

    def test_enriched_text_improves_persona_classification(self) -> None:
        cfg = hn.default_hiring_network_config()
        thin = hn.ProfileCandidate(
            profile_url="https://www.linkedin.com/in/sample-retail-leader/",
            name="Sample Leader",
            headline="Professional",
            company="Apranga",
            location="Vilnius, Lithuania",
            scraped_text="Product support manager",
        )
        rich = hn.ProfileCandidate(
            profile_url="https://www.linkedin.com/in/sample-retail-leader/",
            name="Sample Leader",
            headline="Talent Acquisition Manager",
            company="Apranga Group",
            location="Vilnius, Lithuania",
            scraped_text=(
                "Talent acquisition manager hiring retail leaders in Vilnius. "
                "HR manager recruiting store directors."
            ),
        )
        thin_persona = hn.classify_persona(thin, cfg)
        rich_persona = hn.classify_persona(rich, cfg)
        self.assertEqual(thin_persona.persona, "low_relevance")
        self.assertNotEqual(rich_persona.persona, "low_relevance")


if __name__ == "__main__":
    unittest.main()
