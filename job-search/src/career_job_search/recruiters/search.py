"""LinkedIn people-search query merging for recruiter scouting."""

from __future__ import annotations

from typing import Any

# Substrings that classify a query line as recruiter/HR intent (else hiring_leader).
_RECRUITER_INTENT_MARKERS = (
    "recruiter",
    "talent acquisition",
    "headhunter",
    "human resources",
    " hr ",
    "hr manager",
    "hr business partner",
    "people partner",
    "head of people",
    "head of hr",
    "personalo",
    "įdarbinim",
    "talento pritraukim",
)


def classify_query_intent(query_line: str) -> str:
    """Return ``recruiter`` or ``hiring_leader`` for analytics and rotation."""
    ql = f" {query_line.lower()} "
    if any(m in ql for m in _RECRUITER_INTENT_MARKERS):
        return "recruiter"
    return "hiring_leader"


def _normalize_query(q: str) -> str:
    return " ".join(str(q or "").split()).strip().lower()


def _append_geo(query: str, geo: str) -> str:
    q = query.strip()
    if not q or not geo:
        return q
    gl = geo.lower()
    if gl in q.lower():
        return q
    return f"{q} {geo}".strip()


def merged_queries_for_variant(
    cfg: dict[str, Any],
    variant_slug: str,
) -> list[tuple[str, str]]:
    """
    Merge ``search.queries_by_variant`` and ``hiring_network.persona_search_queries``.

    Returns deduped ``(query_line, search_intent)`` tuples.
    """
    search = cfg.get("search") or {}
    geo = str(search.get("default_geo_keyword") or "").strip()

    base_map = search.get("queries_by_variant") or {}
    hn = cfg.get("hiring_network") or {}
    persona_map = hn.get("persona_search_queries") or {}

    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(q: str, intent: str | None = None) -> None:
        line = _append_geo(str(q or "").strip(), geo)
        if not line:
            return
        key = _normalize_query(line)
        if key in seen:
            return
        seen.add(key)
        out.append((line, intent or classify_query_intent(line)))

    if isinstance(base_map, dict):
        for q in base_map.get(variant_slug) or []:
            if isinstance(q, str):
                add(q, None)

    if isinstance(persona_map, dict):
        for q in persona_map.get(variant_slug) or []:
            if isinstance(q, str):
                add(q, "hiring_leader")

    return out


def merged_queries_by_variant(cfg: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    """All variants with merged query lists."""
    search = cfg.get("search") or {}
    base_map = search.get("queries_by_variant") or {}
    if not isinstance(base_map, dict):
        return {}
    return {
        slug: merged_queries_for_variant(cfg, slug)
        for slug in base_map
        if isinstance(slug, str)
    }
