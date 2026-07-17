"""Domain records shared by recruiter web integrations and caches."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WebSearchHit:
    title: str = ""
    url: str = ""
    snippet: str = ""
    source: str = ""


@dataclass
class WebResearchResult:
    query: str
    hits: list[WebSearchHit] = field(default_factory=list)
    backend: str = ""
    error: str = ""


@dataclass
class CandidateEvidence:
    """Deepened evidence for a single candidate before outreach."""

    profile_url: str
    personalization_text: str = ""
    sourcing_keywords: str = ""
    source: str = ""
