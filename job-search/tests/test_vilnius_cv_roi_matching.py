from __future__ import annotations

import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from matching_lib import (  # noqa: E402
    load_profiles,
    match_job_to_variants,
    parse_job_file,
)


def _match(raw_job: str) -> dict:
    return match_job_to_variants(parse_job_file(raw_job), load_profiles())


def test_business_process_job_prefers_ba_ops_variant() -> None:
    result = _match(
        """
TITLE: Business Process Analyst
COMPANY: Global Services Vilnius
SOURCE: linkedin
---
We need a business process analyst for process mapping, requirements gathering,
stakeholder management, KPI reporting, workflow documentation, UAT support,
CRM data quality, continuous improvement, and operations coordination.
"""
    )

    assert result["recommendation"]["variant_slug"] == "business-process-operations"


def test_customer_success_job_prefers_ba_ops_bridge_variant() -> None:
    result = _match(
        """
TITLE: Customer Success Manager
COMPANY: SaaS Ecommerce Platform
SOURCE: work_in_lt
---
You will handle customer success, onboarding, customer operations, escalation
handling, retention, renewals, customer health, CRM updates, KPI reporting,
service recovery, and stakeholder follow-up for ecommerce clients.
"""
    )

    assert result["recommendation"]["variant_slug"] == "business-process-operations"


def test_lithuanian_retail_job_prefers_lithuanian_retail_variant() -> None:
    result = _match(
        """
TITLE: Parduotuvės vadovas
COMPANY: Premium Fashion Vilnius
SOURCE: cvbank
---
Ieškome parduotuvės vadovo Vilniuje. Svarbu prabangos ir premium prekybos
patirtis, klientų aptarnavimas, klientų patirtis, vizualinis prekių pateikimas,
KPI, konversija, komandos ugdymas, atsargų papildymas ir kasa.
"""
    )

    assert result["recommendation"]["variant_slug"] in {"luxury-retail-lt", "luxury-retail"}


def test_exact_lithuanian_target_title_routes_to_lithuanian_variant() -> None:
    result = _match(
        """
TITLE: Salono vadovas
COMPANY: Premium Cosmetics Vilnius
SOURCE: cvbank
---
Lead premium retail operations, active sales, service standards, stock control,
team coordination, reporting, and visual presentation in a Vilnius salon.
"""
    )

    assert result["recommendation"]["variant_slug"] == "luxury-retail-lt"
    top = result["variants_ranked"][0]
    assert "Salono vadovas" in top["target_title_hits"]
