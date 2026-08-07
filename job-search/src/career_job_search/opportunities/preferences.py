"""Private, editable search preferences for the local career workspace."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from career_job_search.core.contracts import helper_json
from career_job_search.core.paths import project_path
from career_job_search.core.time import utc_now_iso

DEFAULT_SEARCH_PREFERENCES_PATH = project_path("state", "search_preferences.json")

WorkArrangement = Literal["on_site", "hybrid", "remote_lithuania", "remote_eu"]


class SearchPreferences(BaseModel):
    """Human-owned preferences. They guide ranking but never auto-apply."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["career_search_preferences_v1"] = Field(
        default="career_search_preferences_v1",
        alias="schema",
    )
    target_roles: list[str] = Field(
        default_factory=lambda: [
            "business process operations",
            "customer operations",
            "implementation manager",
            "retail operations",
            "store manager",
        ],
        max_length=20,
    )
    priority_locations: list[str] = Field(
        default_factory=lambda: ["Vilnius", "Lithuania", "Remote EU"],
        max_length=20,
    )
    work_arrangements: list[WorkArrangement] = Field(
        default_factory=lambda: [
            "on_site",
            "hybrid",
            "remote_lithuania",
            "remote_eu",
        ],
        min_length=1,
        max_length=4,
    )
    minimum_salary_eur_monthly: int | None = Field(
        default=None,
        ge=0,
        le=100_000,
    )
    excluded_keywords: list[str] = Field(default_factory=list, max_length=50)
    excluded_companies: list[str] = Field(default_factory=list, max_length=50)
    daily_queue_size: int = Field(default=5, ge=5, le=10)
    updated_at: str = ""

    @field_validator(
        "target_roles",
        "priority_locations",
        "excluded_keywords",
        "excluded_companies",
    )
    @classmethod
    def clean_text_list(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                raise ValueError("Preference lists may contain text only.")
            item = " ".join(value.split()).strip()
            if not item:
                continue
            if len(item) > 80:
                raise ValueError(
                    "Each search preference must be 80 characters or fewer."
                )
            identity = item.casefold()
            if identity in seen:
                continue
            seen.add(identity)
            cleaned.append(item)
        return cleaned

    @field_validator("work_arrangements")
    @classmethod
    def deduplicate_work_arrangements(
        cls, values: list[WorkArrangement]
    ) -> list[WorkArrangement]:
        return list(dict.fromkeys(values))


def default_search_preferences() -> SearchPreferences:
    return SearchPreferences()


def load_search_preferences(
    path: Path | str = DEFAULT_SEARCH_PREFERENCES_PATH,
) -> SearchPreferences:
    preference_path = Path(path)
    if not preference_path.exists():
        return default_search_preferences()
    try:
        payload = json.loads(preference_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Search preferences could not be read: {preference_path}"
        ) from exc
    try:
        return SearchPreferences.model_validate(payload)
    except ValueError as exc:
        raise ValueError(f"Search preferences are invalid: {preference_path}") from exc


def save_search_preferences(
    payload: dict[str, Any] | SearchPreferences,
    *,
    path: Path | str = DEFAULT_SEARCH_PREFERENCES_PATH,
) -> SearchPreferences:
    data = (
        payload.model_dump(by_alias=True)
        if isinstance(payload, SearchPreferences)
        else payload
    )
    preferences = SearchPreferences.model_validate(data)
    preferences.updated_at = utc_now_iso()

    preference_path = Path(path)
    preference_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = preference_path.with_suffix(preference_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(preferences.model_dump(by_alias=True), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(preference_path)
    os.chmod(preference_path, 0o600)
    return preferences


def apply_search_preferences(
    config: dict[str, Any], preferences: SearchPreferences
) -> dict[str, Any]:
    """Return a copy of discovery config influenced by human-owned preferences."""

    updated = copy.deepcopy(config)
    opportunities = updated.setdefault("opportunities", {})
    if not isinstance(opportunities, dict):
        raise ValueError("Opportunity config 'opportunities' must be a mapping.")

    geography = opportunities.setdefault("geography", {})
    scoring = opportunities.setdefault("scoring", {})
    sources = opportunities.setdefault("sources", {})
    if not all(isinstance(item, dict) for item in (geography, scoring, sources)):
        raise ValueError(
            "Opportunity geography, scoring, and sources must be mappings."
        )

    if preferences.priority_locations:
        geography["default_regions"] = list(preferences.priority_locations)
        scoring["priority_regions"] = list(preferences.priority_locations)

    tracks = [
        track
        for track in list(scoring.get("role_tracks") or [])
        if isinstance(track, dict) and track.get("name") != "user_search_profile"
    ]
    if preferences.target_roles:
        tracks.append(
            {
                "name": "user_search_profile",
                "weight": 1.5,
                "keywords": list(preferences.target_roles),
            }
        )
    scoring["role_tracks"] = tracks

    linkedin = sources.get("linkedin")
    if isinstance(linkedin, dict) and preferences.target_roles:
        linkedin["queries"] = list(preferences.target_roles[:6])
    return updated


def _text_match(items: list[str], haystack: str) -> str:
    return next((item for item in items if item.casefold() in haystack), "")


def _arrangement_for_row(row: dict[str, Any]) -> WorkArrangement | None:
    eligibility = str(row.get("location_eligibility") or "")
    policy = str(row.get("remote_policy") or "").casefold()
    location = str(row.get("location") or "").casefold()
    if eligibility == "eligible_eu_remote" or "remote eu" in policy:
        return "remote_eu"
    if eligibility == "eligible_lt_remote" or "remote lithuania" in policy:
        return "remote_lithuania"
    if "hybrid" in policy or "hybrid" in location:
        return "hybrid"
    if "vilnius" in location or eligibility == "eligible_vilnius":
        return "on_site"
    return None


def _salary_monthly_eur(row: dict[str, Any]) -> int | None:
    text = str(row.get("salary_text") or "").casefold()
    if not text or not any(marker in text for marker in ("eur", "€")):
        return None
    values: list[float] = []
    for raw, suffix in re.findall(r"(\d[\d ,.]*\d|\d)(\s*k)?", text):
        normalized = raw.replace(" ", "").replace(",", ".")
        try:
            value = float(normalized)
        except ValueError:
            continue
        if suffix.strip():
            value *= 1_000
        if value >= 100:
            values.append(value)
    if not values:
        return None
    salary = min(values)
    if any(marker in text for marker in ("year", "annual", "annum", "/yr")):
        salary /= 12
    return round(salary)


def evaluate_search_preferences(
    row: dict[str, Any], preferences: SearchPreferences
) -> dict[str, Any]:
    """Explain preference fit and identify only explicit hard exclusions."""

    match = row.get("match") or {}
    searchable = " ".join(
        str(value or "")
        for value in (
            row.get("title"),
            row.get("company"),
            row.get("location"),
            row.get("remote_policy"),
            row.get("description"),
            match.get("role_track"),
        )
    ).casefold()
    company = str(row.get("company") or "").casefold()
    reasons: list[str] = []
    flags: list[str] = []
    score = 0

    target = _text_match(preferences.target_roles, searchable)
    if target:
        reasons.append(f"Matches your target role: {target}")
        score += 3

    location = _text_match(preferences.priority_locations, searchable)
    if location:
        reasons.append(f"Matches your preferred location: {location}")
        score += 2

    arrangement = _arrangement_for_row(row)
    if arrangement and arrangement in preferences.work_arrangements:
        labels = {
            "on_site": "on-site in Vilnius",
            "hybrid": "hybrid",
            "remote_lithuania": "remote in Lithuania",
            "remote_eu": "remote in the EU",
        }
        reasons.append(f"Matches your work setup: {labels[arrangement]}")
        score += 1
    elif arrangement:
        flags.append("work_arrangement_not_selected")

    excluded_company = _text_match(preferences.excluded_companies, company)
    if excluded_company:
        flags.append("excluded_company")

    excluded_keyword = _text_match(preferences.excluded_keywords, searchable)
    if excluded_keyword:
        flags.append("excluded_keyword")

    salary = _salary_monthly_eur(row)
    if preferences.minimum_salary_eur_monthly and salary is not None:
        if salary >= preferences.minimum_salary_eur_monthly:
            reasons.append("Disclosed salary meets your minimum")
            score += 1
        else:
            flags.append("salary_below_minimum")

    if not reasons:
        reasons.append("Recommended from CV fit and current role evidence")
    return {
        "eligible": not {"excluded_company", "excluded_keyword"}.intersection(flags),
        "score": score,
        "reasons": reasons[:3],
        "flags": flags,
    }


def _json_response(payload: dict[str, Any]) -> None:
    print(helper_json(payload))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage local search preferences")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show")
    save = subparsers.add_parser("save")
    save.add_argument("--json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "show":
            preferences = load_search_preferences()
        else:
            raw = json.loads(args.json)
            if not isinstance(raw, dict):
                raise ValueError("Search preferences must be a JSON object.")
            preferences = save_search_preferences(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        _json_response({"ok": False, "error": str(exc)})
        return 1
    _json_response({"ok": True, "data": preferences.model_dump(by_alias=True)})
    return 0


if __name__ == "__main__":
    from career_job_search.core.entrypoint import entry
    from career_job_search.core.schema import SEARCH_PREFERENCES_SCHEMA

    entry(SEARCH_PREFERENCES_SCHEMA, main)
