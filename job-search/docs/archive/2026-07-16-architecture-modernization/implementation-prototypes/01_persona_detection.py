#!/usr/bin/env python3
"""
Recruiter Persona Detection & Authority Weighting

Add this to job-search/tools/recruiter_match.py to classify recruiters by persona
and authority level. Enables tier rules to require minimum authority levels.

Usage:
    from recruiter_match import detect_recruiter_persona

    persona, authority = detect_recruiter_persona(profile_blob_lower="vp people at michael kors")
    print(persona, authority)  # Output: ('internal_hr_leader', 90)

Integration:
    1. Add PERSONA_AUTHORITY_WEIGHTS and detect_recruiter_persona() to recruiter_match.py
    2. In match_recruiter_profile(), call: persona, authority = detect_recruiter_persona(blob_lower)
    3. Add to result['recruiter_meta']: {'persona_slug': persona, 'persona_authority': authority}
    4. In assign_best_tier(), check: if persona_authority < tier_rule.get('min_persona_authority', 0): skip
    5. Update tier rules in config.yaml with min_persona_authority gates

Generated: 20 May 2026 | Desktop Commander Recommendations
"""

from __future__ import annotations

# Authority weights: higher = more hiring authority/power
PERSONA_AUTHORITY_WEIGHTS = {
    "executive_search": 95,           # C-level gatekeeper, retained search consultant
    "internal_hr_leader": 90,         # VP People, Chief People Officer, Head of HR
    "hiring_manager": 85,             # Area Manager, Store Director, Regional Manager with hiring power
    "in_house_recruiter": 80,         # Corporate recruiter, internal talent team
    "staffing_agency_recruiter": 70,  # Michael Page, Experis, generalist recruiter
    "generic_hr": 60,                 # HR Admin, HR Generalist, HR Coordinator
    "unknown": 0,                     # No hiring signal detected
}


def detect_recruiter_persona(blob_lower: str) -> tuple[str, int]:
    """
    Classify recruiter by persona and return authority weight.

    Args:
        blob_lower: Concatenated, lowercased profile text (headline + company + about + location)

    Returns:
        (persona_slug, authority_weight)
        - persona_slug: 'executive_search', 'internal_hr_leader', 'hiring_manager', etc.
        - authority_weight: 0–95 (higher = more hiring authority)

    Examples:
        >>> detect_recruiter_persona("vp people at michael kors, hiring leaders")
        ('internal_hr_leader', 90)

        >>> detect_recruiter_persona("retained search consultant, executive recruitment")
        ('executive_search', 95)

        >>> detect_recruiter_persona("michael page, retail recruiter")
        ('staffing_agency_recruiter', 70)

        >>> detect_recruiter_persona("area manager retail, vilnius")
        ('hiring_manager', 85)
    """

    # Layer 1: Executive Search (highest authority)
    if any(term in blob_lower for term in [\n        "executive search",\n        "retained search",\n        "executive recruitment",\n        "c-level recruiter",\n        "c level recruiter",\n        "search consultant",\n        "leadership advisory",\n        "korn ferry",\n        "heidrick & struggles",\n        "spencer stuart",\n    ]):\n        return ("executive_search", 95)\n    \n    # Layer 2: Internal HR Leadership (VP+ level, direct hiring authority)\n    if any(term in blob_lower for term in [\n        "vp people\",\n        \"vp hr\",\n        \"chief people\",\n        \"chief people officer\",\n        \"head of hr\",\n        \"head of people\",\n        \"head of talent\",\n        \"director of people\",\n        \"senior director hr\",\n    ]):\n        return ("internal_hr_leader", 90)\n    \n    # Layer 3: Hiring Manager (team-level hiring authority)\n    if any(term in blob_lower for term in [\n        "hiring manager\",\n        \"area manager\",\n        \"regional manager\",\n        \"district manager\",\n        \"cluster manager\",\n        \"country manager\",\n        \"store director\",\n        \"store manager\",\n        \"retail director\",\n        \"operations director\",\n        \"general manager\",\n        \"head of retail\",\n        \"head of stores\",\n    ]):\n        return ("hiring_manager", 85)\n    \n    # Layer 4: In-House Recruiter (corporate talent team)\n    if any(term in blob_lower for term in [\n        "in-house recruiter\",\n        \"in house recruiter\",\n        \"corporate recruiter\",\n        \"internal recruiter\",\n        \"talent partner\",\n        \"sr. recruiter\",\n        \"senior recruiter\",\n        \"recruiting manager\",\n        \"talent acquisition manager\",\n        \"talent acquisition lead\",\n    ]):\n        return ("in_house_recruiter", 80)\n    \n    # Layer 5: Staffing Agency Recruiter (external, high volume)\n    if any(term in blob_lower for term in [\n        "michael page\",\n        \"experis\",\n        \"korn ferry\",\n        \"heidrick\",\n        \"spencer stuart\",\n        \"recruiter\",\n        \"talent acquisition\",\n        \"recruitment\",\n        \"staffing\",\n        \"headhunter\",\n        \"talent scout\",\n        \"recruitment specialist\",\n        \"recruitment consultant\",\n    ]):\n        # But exclude if already matched higher layers\n        # (Already handled above, so this catches generalist recruiters)\n        return ("staffing_agency_recruiter", 70)\n    \n    # Layer 6: Generic HR (no hiring responsibility)\n    if any(term in blob_lower for term in [\n        \"hr manager\",\n        \"hr business partner\",\n        \"hr generalist\",\n        \"hr coordinator\",\n        \"people operations\",\n        \"people & culture\",\n        \"people and culture\",\n        \"people ops\",\n        \"human resources\",\n        \"hr administrator\",\n        \"hr specialist\",\n        \"personalo\",  # Lithuanian\n        \"personalo vadovas\",\n        \"personalo specialistas\",\n    ]):\n        return ("generic_hr", 60)\n    \n    return ("unknown", 0)\n\n\ndef describe_persona(persona_slug: str, authority: int) -> str:\n    \"\"\"\n    Human-readable description of persona & authority.\n    \n    Usage (for logging):\n        persona, auth = detect_recruiter_persona(blob)\n        print(describe_persona(persona, auth))\n        # Output: \"Internal HR Leader (authority: 90)\"\n    \"\"\"\n    descriptions = {\n        "executive_search": f"Executive Search (retained, C-level access) — authority {authority}\",\n        \"internal_hr_leader\": f\"Internal HR Leader (VP+, direct hiring) — authority {authority}\",\n        \"hiring_manager\": f\"Hiring Manager (team-level, area/store) — authority {authority}\",\n        \"in_house_recruiter\": f\"In-House Recruiter (corporate talent) — authority {authority}\",\n        \"staffing_agency_recruiter\": f\"Staffing Agency Recruiter (external) — authority {authority}\",\n        \"generic_hr\": f\"Generic HR (admin, no hiring) — authority {authority}\",\n        \"unknown\": f\"Unknown/Other — authority {authority}\",\n    }\n    return descriptions.get(persona_slug, f\"Unknown persona {persona_slug} — authority {authority}\")\n\n\n# ============================================================================\n# INTEGRATION CHECKLIST\n# ============================================================================\n# \n# To integrate this into your recruiter matching:\n#\n# 1. Copy detect_recruiter_persona() and PERSONA_AUTHORITY_WEIGHTS into:\n#    job-search/tools/recruiter_match.py (after imports, before other functions)\n#\n# 2. In match_recruiter_profile() (around line 239):\n#    \n#    # Add after creating blob_lower:\n#    persona_slug, persona_authority = detect_recruiter_persona(blob_lower)\n#    \n#    # Store in result:\n#    result[\"recruiter_meta\"][\"persona_slug\"] = persona_slug\n#    result[\"recruiter_meta\"][\"persona_authority\"] = persona_authority\n#\n# 3. In assign_best_tier() (around line 380):\n#\n#    def assign_best_tier(*, result, cfg, company_blob_lower):\n#        meta = result.get(\"recruiter_meta\") or {}\n#        persona_authority = meta.get(\"persona_authority\", 0)\n#        \n#        for tk in sorted_tier_keys(cfg):\n#            rule = cfg.get(\"tiers\", {}).get(tk, {})\n#            \n#            # NEW: Check persona authority gate\n#            min_auth = rule.get(\"min_persona_authority\", 0)\n#            if persona_authority < min_auth:\n#                continue  # Skip this tier, try next\n#            \n#            # ... rest of tier matching logic ...\n#\n# 4. Update linkedin/config.yaml to add persona authority gates:\n#\n#    tiers:\n#      tier_1:\n#        min_primary_score: 15\n#        min_persona_authority: 85  # NEW: Only exec search, in-house, hiring managers\n#      tier_2:\n#        min_primary_score: 12\n#        min_persona_authority: 70  # NEW: Staffing recruiters OK, but not generic HR\n#      tier_3:\n#        min_primary_score: 13\n#        min_persona_authority: 0   # Optional: accept any persona (backlog)\n#\n# 5. Test:\n#    python3 tools/recruiter_orchestrate.py scout --headed --max 3 --variant luxury-retail\n#    python3 tools/recruiter_orchestrate.py daily --headed --dry-run\n#    \n#    Then inspect log: Do Michael Page recruiters (authority=70) now fail Tier 1 gate?\n#    Do exec search consultants (authority=95) now pass Tier 1?\n#\n# ============================================================================\n\n\nif __name__ == \"__main__\":\n    # Quick test\n    test_cases = [\n        (\"vp people at michael kors, 20 years hiring leaders\", \"internal_hr_leader\", 90),\n        (\"executive search consultant, retained search for c-suite\", \"executive_search\", 95),\n        (\"michael page, senior recruiter, retail talent\", \"staffing_agency_recruiter\", 70),\n        (\"area manager vilnius, retail operations, hiring\", \"hiring_manager\", 85),\n        (\"in-house recruiter, corporate talent team\", \"in_house_recruiter\", 80),\n        (\"hr manager, generalist, hr coordinator\", \"generic_hr\", 60),\n    ]\n    \n    for blob, expected_persona, expected_auth in test_cases:\n        persona, auth = detect_recruiter_persona(blob.lower())\n        status = \"✅\" if persona == expected_persona and auth == expected_auth else \"❌\"\n        print(f\"{status} {blob}\")\n        print(f\"   → {describe_persona(persona, auth)}\")\n        print()\n
