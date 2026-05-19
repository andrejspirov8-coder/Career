"""LangChain tools for Ollama agent tool-calling (read-only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from matching_lib import PROFILES_PATH
from recruiter_agent_context import _company_history
from recruiter_persona_stats import load_persona_stats

CV_DIR = Path(__file__).resolve().parent.parent / "cv"

_TOOL_REGISTRY: dict[str, Any] = {}


def _tool_lookup_company_history(company: str) -> str:
    if not company.strip():
        return json.dumps({"error": "company required"})
    return json.dumps(_company_history(company), ensure_ascii=False)


def _tool_lookup_persona_stats(persona: str) -> str:
    stats = load_persona_stats()
    entry = stats.get(persona) or {"sent": 0, "accepted": 0, "rate": 0.0}
    return json.dumps(entry, ensure_ascii=False)


def _tool_lookup_candidate_evidence(profile_url: str) -> str:
    if not profile_url.strip():
        return json.dumps({"error": "profile_url required"})
    try:
        import recruiter_match as rm

        result = rm.match_recruiter_profile(
            headline="LinkedIn profile",
            profile_url=profile_url,
            recruiter_cfg={"recruiter_matching": {"sector_beats_cv_min_score": 6}},
        )
        hits = (result.get("variants_ranked") or [{}])[0].get("keyword_hits") or []
        return json.dumps(
            {"keyword_hits": [str(x) for x in hits[:5]]}, ensure_ascii=False
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _tool_count_chars(text: str) -> str:
    return str(len(" ".join((text or "").split())))


def _tool_get_cv_blurb(variant_slug: str) -> str:
    if not PROFILES_PATH.is_file():
        return variant_slug
    raw = yaml.safe_load(PROFILES_PATH.read_text(encoding="utf-8")) or {}
    block = (raw.get("variants") or {}).get(variant_slug) or {}
    if not isinstance(block, dict):
        return variant_slug
    titles = block.get("target_titles") or []
    return (f"{variant_slug}: " + ", ".join(str(t) for t in titles[:3]))[:200]


def _ensure_tools() -> dict[str, Any]:
    if _TOOL_REGISTRY:
        return _TOOL_REGISTRY
    try:
        from langchain_core.tools import tool
    except ImportError:
        return {}

    @tool
    def lookup_company_history(company: str) -> str:
        """Return sent/accepted counts and last contact date for a company."""
        return _tool_lookup_company_history(company)

    @tool
    def lookup_persona_stats(persona: str) -> str:
        """Return sent, accepted, and accept rate for a hiring persona."""
        return _tool_lookup_persona_stats(persona)

    @tool
    def lookup_candidate_evidence(profile_url: str) -> str:
        """Return top keyword hits for a LinkedIn profile URL."""
        return _tool_lookup_candidate_evidence(profile_url)

    @tool
    def count_chars(text: str) -> str:
        """Count characters in text after collapsing whitespace."""
        return _tool_count_chars(text)

    @tool
    def get_cv_blurb(variant_slug: str) -> str:
        """Return a one-line CV pitch for a variant slug."""
        return _tool_get_cv_blurb(variant_slug)

    _TOOL_REGISTRY.update(
        {
            "lookup_company_history": lookup_company_history,
            "lookup_persona_stats": lookup_persona_stats,
            "lookup_candidate_evidence": lookup_candidate_evidence,
            "count_chars": count_chars,
            "get_cv_blurb": get_cv_blurb,
        }
    )
    return _TOOL_REGISTRY


def tools_for_agent(full_cfg: dict[str, Any], agent_name: str) -> list[Any]:
    registry = _ensure_tools()
    if not registry:
        return []
    names = agent_cfg_names(full_cfg, agent_name)
    return [registry[n] for n in names if n in registry]


def agent_cfg_names(full_cfg: dict[str, Any], agent_name: str) -> list[str]:
    agents = (full_cfg.get("llm") or {}).get("agents") or {}
    block = agents.get(agent_name) or {}
    raw = block.get("tools") or []
    return [str(x) for x in raw if x]


def dispatch_tool_call(call: dict[str, Any], tools: list[Any]) -> str:
    name = str(call.get("name") or "")
    args = call.get("args") or {}
    by_name = {getattr(t, "name", ""): t for t in tools}
    fn = by_name.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        return str(fn.invoke(args))
    except Exception as exc:
        return json.dumps({"error": str(exc)})
