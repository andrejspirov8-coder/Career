"""Strict location eligibility classification for opportunities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from career_job_search.opportunities.models import Opportunity

LocationEligibility = Literal[
    "eligible_vilnius",
    "eligible_lt_remote",
    "eligible_eu_remote",
    "verify_remote",
    "ineligible",
]
WorkMode = Literal["onsite", "hybrid", "remote", "unknown"]


@dataclass(frozen=True)
class EligibilityResult:
    eligibility: LocationEligibility
    reason: str
    work_mode: WorkMode


_CONFIRMED_ELIGIBILITY = frozenset(
    {"eligible_vilnius", "eligible_lt_remote", "eligible_eu_remote"}
)
_VILNIUS_TOKENS = frozenset({"vilnius", "vilniaus", "vilniuje"})
_LITHUANIA_TOKENS = frozenset({"lithuania", "lietuva", "lt"})
_REMOTE_TOKENS = frozenset(
    {
        "remote",
        "remotely",
        "anywhere",
        "everywhere",
        "worldwide",
        "global",
        "wfh",
    }
)
_HYBRID_TOKENS = frozenset({"hybrid", "hibrid"})
_FOREIGN_COUNTRY_TOKENS = frozenset(
    {
        "albania",
        "andorra",
        "armenia",
        "australia",
        "austria",
        "azerbaijan",
        "belarus",
        "belgium",
        "bosnia",
        "bulgaria",
        "canada",
        "china",
        "croatia",
        "cyprus",
        "czech",
        "czechia",
        "denmark",
        "england",
        "estonia",
        "finland",
        "france",
        "georgia",
        "germany",
        "greece",
        "hungary",
        "iceland",
        "india",
        "ireland",
        "italy",
        "japan",
        "kazakhstan",
        "kosovo",
        "latvia",
        "liechtenstein",
        "luxembourg",
        "macedonia",
        "malta",
        "marino",
        "moldova",
        "monaco",
        "montenegro",
        "netherlands",
        "norway",
        "poland",
        "portugal",
        "romania",
        "russia",
        "scotland",
        "serbia",
        "slovakia",
        "slovenia",
        "spain",
        "sweden",
        "switzerland",
        "turkey",
        "türkiye",
        "uk",
        "ukraine",
        "vatican",
        "wales",
    }
)
_FOREIGN_REGION_TOKENS = frozenset({"apac", "latam"})
_NON_EXCLUSIVE_REMOTE_SCOPE_TOKENS = frozenset(
    {
        "anywhere",
        "baltic",
        "baltics",
        "eea",
        "emea",
        "eu",
        "europe",
        "everywhere",
        "global",
        "home",
        "lt",
        "lietuva",
        "lithuania",
        "worldwide",
    }
)
_GEOGRAPHY_SCOPE_TOKENS = (
    _FOREIGN_COUNTRY_TOKENS
    | _FOREIGN_REGION_TOKENS
    | _LITHUANIA_TOKENS
    | _NON_EXCLUSIVE_REMOTE_SCOPE_TOKENS
    | {
        "america",
        "european",
        "kingdom",
        "north",
        "south",
        "states",
        "union",
        "united",
        "us",
        "usa",
    }
)
_GEOGRAPHY_SCOPE_FILLERS = frozenset(
    {"across", "and", "from", "in", "of", "only", "or", "region", "the", "within"}
)
_FOREIGN_SCOPE_PATTERN = (
    r"(?:united\s+states|united\s+kingdom|north\s+america|south\s+america|"
    + "|".join(
        re.escape(country)
        for country in sorted(
            _FOREIGN_COUNTRY_TOKENS | _FOREIGN_REGION_TOKENS | {"us", "usa"},
            key=len,
            reverse=True,
        )
    )
    + r")"
)
_FOREIGN_SCOPE_RE = re.compile(rf"\b{_FOREIGN_SCOPE_PATTERN}\b")
_FOREIGN_ONLY_RE = re.compile(
    rf"\b{_FOREIGN_SCOPE_PATTERN}(?:\s+remote)?\s+only\b"
    rf"|\bonly\s+{_FOREIGN_SCOPE_PATTERN}\b"
)
_FOREIGN_PEOPLE_ONLY_RE = re.compile(
    rf"\b{_FOREIGN_SCOPE_PATTERN}(?:\s+based)?\s+"
    rf"(?:residents?|candidates?|workers?)\s+only\b"
)
_REMOTE_RESTRICTED_SCOPE_RE = re.compile(
    r"\bremote\s+(?:within|in|from)\s+(?:the\s+)?(.+)$"
)
_REMOTE_SCOPED_ONLY_RE = re.compile(r"\bremote\s+([a-z]+)\s+only\b")
_RESIDENCY_RE = re.compile(
    r"\b(?:candidates?|applicants?|employees?|workers?)?\s*"
    r"(?:must|required\s+to)\s+"
    r"(?:reside|live|be\s+based|be\s+located)\s+in\s+"
    r"(?:the\s+)?(.+)$"
)


def _normalise(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", (value or "").casefold()))


def _tokens(value: str) -> set[str]:
    return set(_normalise(value).split())


def _has_phrase(value: str, phrase: str) -> bool:
    return f" {phrase} " in f" {_normalise(value)} "


def _normalised_clauses(value: str) -> list[str]:
    return [
        normalised
        for clause in re.split(r"[.;\n]+", value or "")
        if (normalised := _normalise(clause))
    ]


def _remote_is_negated(remote_policy: str) -> bool:
    normalised = _normalise(remote_policy)
    if re.search(r"\bno\s+remote\s+restrictions?\b", normalised):
        return False
    return bool(
        re.search(r"\b(?:not|no)\s+remote\b", normalised)
        or re.search(
            r"\bremote(?:\s+work)?\s+(?:is\s+)?"
            r"(?:not\s+available|unavailable|not\s+offered)\b",
            normalised,
        )
    )


def _detect_work_mode(location: str, remote_policy: str) -> WorkMode:
    policy_tokens = _tokens(remote_policy)
    location_tokens = _tokens(location)
    structured_tokens = policy_tokens | location_tokens
    structured = f"{location} {remote_policy}"

    if structured_tokens & _HYBRID_TOKENS:
        return "hybrid"
    if _remote_is_negated(remote_policy):
        return "onsite" if location.strip() else "unknown"
    if (
        structured_tokens & _REMOTE_TOKENS
        or _has_phrase(structured, "work from home")
        or _has_phrase(structured, "home based")
    ):
        return "remote"
    if (
        "onsite" in structured_tokens
        or _has_phrase(structured, "on site")
        or _has_phrase(structured, "office based")
        or _has_phrase(structured, "in office")
    ):
        return "onsite"

    policy_geography = (
        policy_tokens & (_LITHUANIA_TOKENS | _FOREIGN_COUNTRY_TOKENS)
        or policy_tokens & _FOREIGN_REGION_TOKENS
        or policy_tokens & {"eu", "eea", "europe", "emea", "usa", "uk"}
        or _has_phrase(remote_policy, "european union")
        or _has_phrase(remote_policy, "united states")
        or _has_phrase(remote_policy, "united kingdom")
    )
    if policy_geography:
        return "remote"
    if location.strip():
        return "onsite"
    return "unknown"


def _explicitly_excludes_lithuania(structured: str) -> bool:
    lithuania = r"(?:lithuania|lietuva|lt)"
    before = (
        rf"\b(?:except(?:\s+for)?|excluding|excludes?|excluded|outside|"
        rf"but\s+not|other\s+than|apart\s+from|"
        rf"(?:with\s+)?the\s+exception\s+of|"
        rf"not\s+available(?:\s+to\s+(?:candidates|residents|applicants))?\s+in|"
        rf"not\s+open(?:\s+to\s+(?:candidates|residents|applicants))?\s+in|"
        rf"unavailable\s+in|cannot\s+hire\s+in|"
        rf"can\s+not\s+hire\s+in)\s+{lithuania}\b"
    )
    after = (
        rf"\b{lithuania}\s+(?:is\s+)?(?:excluded|not\s+allowed|"
        rf"not\s+available|not\s+eligible|not\s+supported|unavailable)\b"
    )
    broad_but = rf"\b(?:anywhere|everywhere|worldwide)\s+but\s+{lithuania}\b"
    normalised = _normalise(structured)
    return bool(
        re.search(before, normalised)
        or re.search(after, normalised)
        or re.search(broad_but, normalised)
    )


def _without_exclusion_clause(value: str) -> str:
    return re.split(
        r"\b(?:except(?:\s+for)?|excluding|excludes?|but(?:\s+not)?|"
        r"other\s+than|apart\s+from|(?:with\s+)?the\s+exception\s+of)\b",
        _normalise(value),
        maxsplit=1,
    )[0].strip()


def _has_non_exclusive_remote_scope(value: str) -> bool:
    tokens = _tokens(value)
    return bool(
        tokens & _NON_EXCLUSIVE_REMOTE_SCOPE_TOKENS
        or _has_phrase(value, "european union")
    )


def _is_geography_only_scope(value: str) -> bool:
    tokens = _tokens(value)
    return bool(
        tokens & _GEOGRAPHY_SCOPE_TOKENS
        and tokens <= (_GEOGRAPHY_SCOPE_TOKENS | _GEOGRAPHY_SCOPE_FILLERS)
    )


def _has_remote_signal(value: str) -> bool:
    tokens = _tokens(value)
    return bool(
        tokens & _REMOTE_TOKENS
        or _has_phrase(value, "work from home")
        or _has_phrase(value, "home based")
    )


def _remote_scope_clauses(location: str, remote_policy: str) -> list[str]:
    scopes = [
        _without_exclusion_clause(clause) for clause in _normalised_clauses(location)
    ]
    scopes.extend(
        scope
        for clause in _normalised_clauses(remote_policy)
        if (
            (scope := _without_exclusion_clause(clause))
            and (_has_remote_signal(scope) or _is_geography_only_scope(scope))
        )
    )
    return [scope for scope in scopes if scope]


def _has_explicit_foreign_only_restriction(value: str) -> bool:
    normalised = _normalise(value)
    if _FOREIGN_ONLY_RE.search(normalised) or _FOREIGN_PEOPLE_ONLY_RE.search(
        normalised
    ):
        return True

    scoped_only = _REMOTE_SCOPED_ONLY_RE.search(normalised)
    return bool(
        scoped_only and not _has_non_exclusive_remote_scope(scoped_only.group(1))
    )


def _has_foreign_residency_restriction(value: str) -> bool:
    for clause in _normalised_clauses(value):
        residency = _RESIDENCY_RE.search(clause)
        if residency and not _has_non_exclusive_remote_scope(residency.group(1)):
            return True
    return False


def _has_foreign_remote_restriction(
    location: str,
    remote_policy: str,
) -> bool:
    structured = f"{location}; {remote_policy}"
    if _has_explicit_foreign_only_restriction(structured):
        return True
    if _has_foreign_residency_restriction(structured):
        return True

    for scope_text in _remote_scope_clauses(location, remote_policy):
        restricted_scope = _REMOTE_RESTRICTED_SCOPE_RE.search(scope_text)
        if restricted_scope:
            if not _has_non_exclusive_remote_scope(restricted_scope.group(1)):
                return True
            continue
        if _FOREIGN_SCOPE_RE.search(scope_text) and not _has_non_exclusive_remote_scope(
            scope_text
        ):
            return True
    return False


def classify_location_eligibility(
    opportunity: Opportunity,
) -> EligibilityResult:
    location = opportunity.location or ""
    remote_policy = opportunity.remote_policy or ""
    work_mode = _detect_work_mode(location, remote_policy)

    if work_mode in {"onsite", "hybrid"}:
        if _tokens(location) & _VILNIUS_TOKENS:
            return EligibilityResult(
                eligibility="eligible_vilnius",
                reason="The structured location explicitly names Vilnius.",
                work_mode=work_mode,
            )
        return EligibilityResult(
            eligibility="ineligible",
            reason="Onsite or hybrid work is not explicitly located in Vilnius.",
            work_mode=work_mode,
        )

    if work_mode == "remote":
        structured = f"{location} {remote_policy}"
        permission_scope = " ".join(_remote_scope_clauses(location, remote_policy))
        permission_tokens = _tokens(permission_scope)

        if _explicitly_excludes_lithuania(structured):
            return EligibilityResult(
                eligibility="ineligible",
                reason="The structured remote restriction excludes Lithuania.",
                work_mode=work_mode,
            )
        if _has_foreign_remote_restriction(location, remote_policy):
            return EligibilityResult(
                eligibility="ineligible",
                reason="The structured remote restriction does not include Lithuania.",
                work_mode=work_mode,
            )
        if permission_tokens & _LITHUANIA_TOKENS:
            return EligibilityResult(
                eligibility="eligible_lt_remote",
                reason="Remote work explicitly allows Lithuania.",
                work_mode=work_mode,
            )
        if permission_tokens & {"eu", "eea"} or _has_phrase(
            permission_scope, "european union"
        ):
            return EligibilityResult(
                eligibility="eligible_eu_remote",
                reason="Remote work explicitly allows the EU or EEA.",
                work_mode=work_mode,
            )
        return EligibilityResult(
            eligibility="verify_remote",
            reason="Remote work is stated, but Lithuania eligibility is not confirmed.",
            work_mode=work_mode,
        )

    return EligibilityResult(
        eligibility="ineligible",
        reason="Structured fields do not establish an eligible work location.",
        work_mode=work_mode,
    )


def is_eligible(result: EligibilityResult) -> bool:
    return result.eligibility in _CONFIRMED_ELIGIBILITY
