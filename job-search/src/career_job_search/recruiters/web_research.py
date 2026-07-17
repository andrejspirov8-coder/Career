"""Pluggable web research backends for recruiter discovery and validation."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Protocol

from career_job_search.recruiters.web_models import (
    CandidateEvidence,
    WebResearchResult,
    WebSearchHit,
)


class WebResearchBackend(Protocol):
    def search(self, query: str, *, num_results: int = 8) -> WebResearchResult: ...


class ExaBackend:
    """Exa REST API (EXA_API_KEY)."""

    name = "web_exa"

    def search(self, query: str, *, num_results: int = 8) -> WebResearchResult:
        api_key = os.environ.get("EXA_API_KEY", "").strip()
        if not api_key:
            return WebResearchResult(
                query=query, backend=self.name, error="EXA_API_KEY not set"
            )
        payload = {
            "query": query,
            "numResults": max(1, min(num_results, 20)),
            "type": "auto",
            "contents": {"text": {"maxCharacters": 1200}},
        }
        req = urllib.request.Request(
            "https://api.exa.ai/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            return WebResearchResult(query=query, backend=self.name, error=str(exc))
        hits: list[WebSearchHit] = []
        for item in raw.get("results") or []:
            if not isinstance(item, dict):
                continue
            hits.append(
                WebSearchHit(
                    title=str(item.get("title") or ""),
                    url=str(item.get("url") or ""),
                    snippet=str(item.get("text") or item.get("snippet") or "")[:1200],
                    source=self.name,
                )
            )
        return WebResearchResult(query=query, hits=hits, backend=self.name)

    def get_contents(
        self, urls: list[str], *, max_characters: int = 3000
    ) -> dict[str, str]:
        """Fetch page text for specific URLs (LinkedIn profiles)."""
        api_key = os.environ.get("EXA_API_KEY", "").strip()
        if not api_key:
            return {}
        clean_urls = [u.strip() for u in urls if u.strip()]
        if not clean_urls:
            return {}
        payload = {
            "urls": clean_urls[:20],
            "text": {"maxCharacters": max(500, min(max_characters, 8000))},
        }
        req = urllib.request.Request(
            "https://api.exa.ai/contents",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError:
            return {}
        out: dict[str, str] = {}
        for item in raw.get("results") or []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            text = str(item.get("text") or "").strip()
            if url and text:
                out[url] = text
        return out


class FirecrawlBackend:
    """Firecrawl CLI search (FIRECRAWL_API_KEY)."""

    name = "web_firecrawl"

    def search(self, query: str, *, num_results: int = 8) -> WebResearchResult:
        if not shutil.which("firecrawl"):
            return WebResearchResult(
                query=query, backend=self.name, error="firecrawl CLI not found"
            )
        cmd = [
            "firecrawl",
            "search",
            query,
            "--limit",
            str(max(1, min(num_results, 20))),
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return WebResearchResult(query=query, backend=self.name, error=str(exc))
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "firecrawl search failed").strip()
            return WebResearchResult(query=query, backend=self.name, error=err[:500])
        try:
            raw = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return WebResearchResult(
                query=query,
                backend=self.name,
                error="firecrawl returned non-JSON output",
            )
        hits: list[WebSearchHit] = []
        items = (
            raw
            if isinstance(raw, list)
            else raw.get("data") or raw.get("results") or []
        )
        for item in items:
            if not isinstance(item, dict):
                continue
            hits.append(
                WebSearchHit(
                    title=str(item.get("title") or ""),
                    url=str(item.get("url") or item.get("link") or ""),
                    snippet=str(
                        item.get("description")
                        or item.get("markdown")
                        or item.get("snippet")
                        or ""
                    )[:1200],
                    source=self.name,
                )
            )
        return WebResearchResult(query=query, hits=hits, backend=self.name)


class OfflineStubBackend:
    """Deterministic offline hits for tests and dry runs."""

    name = "offline_stub"

    def search(self, query: str, *, num_results: int = 8) -> WebResearchResult:
        q = query.lower()
        hits: list[WebSearchHit] = []
        if "luxury" in q or "fashion" in q or "retail" in q:
            hits.append(
                WebSearchHit(
                    title="Area Manager premium retail — Apranga Group",
                    url="https://www.linkedin.com/in/sample-retail-leader/",
                    snippet="Area Manager premium fashion retail Vilnius Lithuania hiring store teams.",
                    source=self.name,
                )
            )
            hits.append(
                WebSearchHit(
                    title="Apranga Group careers",
                    url="https://www.apranga.lt/",
                    snippet="Leading fashion retail group in the Baltics with luxury brands.",
                    source=self.name,
                )
            )
        if "it support" in q or "service desk" in q:
            hits.append(
                WebSearchHit(
                    title="IT Support Manager Vilnius",
                    url="https://www.linkedin.com/in/sample-it-leader/",
                    snippet="IT support manager service desk hiring Lithuania.",
                    source=self.name,
                )
            )
        if "operations" in q:
            hits.append(
                WebSearchHit(
                    title="Operations Director retail Lithuania",
                    url="https://www.linkedin.com/in/sample-ops-leader/",
                    snippet="Multi-site retail operations director hiring regional managers.",
                    source=self.name,
                )
            )
        return WebResearchResult(
            query=query, hits=hits[:num_results], backend=self.name
        )

    def get_contents(
        self, urls: list[str], *, max_characters: int = 3000
    ) -> dict[str, str]:
        out: dict[str, str] = {}
        for url in urls:
            if "/in/sample-" in url or "/in/sample_" in url:
                out[url] = (
                    "# Sample Leader\n\nHR Manager talent acquisition Vilnius retail\n\n"
                    "## About\n\nI lead hiring for premium retail stores across Lithuania.\n\n"
                    "## Experience\n\n### Talent Acquisition Manager at Apranga Group\n"
                    "Vilnius, Lithuania\n\nRecruiting store managers and area leaders."
                )[:max_characters]
        return out


def pick_backend(preferred: str = "auto") -> WebResearchBackend:
    pref = (preferred or "auto").strip().lower()
    if pref == "exa":
        return ExaBackend()
    if pref == "firecrawl":
        return FirecrawlBackend()
    if pref == "offline":
        return OfflineStubBackend()
    if os.environ.get("EXA_API_KEY", "").strip():
        return ExaBackend()
    if shutil.which("firecrawl"):
        return FirecrawlBackend()
    return OfflineStubBackend()


def web_search(
    query: str,
    *,
    num_results: int = 8,
    backend: str = "auto",
    full_cfg: dict | None = None,
    use_cache: bool = True,
) -> WebResearchResult:
    impl = pick_backend(backend)
    if use_cache and full_cfg:
        try:
            from career_job_search.recruiters.web_cache import (
                cache_enabled,
                get_cached,
                put,
            )

            if cache_enabled(full_cfg):
                cached = get_cached(query, impl.name, full_cfg=full_cfg)
                if cached is not None:
                    return cached
        except Exception:
            pass
    result = impl.search(query, num_results=num_results)
    if use_cache and full_cfg and not result.error:
        try:
            from career_job_search.recruiters.web_cache import cache_enabled, put

            if cache_enabled(full_cfg):
                put(query, impl.name, result, full_cfg=full_cfg)
        except Exception:
            pass
    return result


def linkedin_profile_hits(result: WebResearchResult) -> list[WebSearchHit]:
    return [h for h in result.hits if "linkedin.com/in/" in (h.url or "").lower()]


def company_site_hits(result: WebResearchResult) -> list[WebSearchHit]:
    out: list[WebSearchHit] = []
    for hit in result.hits:
        url = (hit.url or "").lower()
        if "linkedin.com/in/" in url:
            continue
        if "linkedin.com/company/" in url or any(
            url.endswith(ext) for ext in (".lt", ".com", ".eu")
        ):
            out.append(hit)
    return out


def fetch_profile_contents(
    urls: list[str],
    *,
    backend: str = "auto",
    max_characters: int = 3000,
) -> dict[str, str]:
    """Return {profile_url: text} for LinkedIn /in/ URLs."""
    impl = pick_backend(backend)
    getter = getattr(impl, "get_contents", None)
    if not callable(getter):
        return {}
    return getter(urls, max_characters=max_characters)


# ── Branch H: Targeted evidence search per candidate ──────────────────────


def _profile_id_from_url(url: str) -> str:
    """Extract LinkedIn profile ID from /in/{profile_id} URL."""
    m = re.search(r"linkedin\.com/in/([^/\?#]+)", (url or "").lower())
    return m.group(1) if m else ""


def search_candidate_evidence(
    profile_url: str,
    name: str = "",
    *,
    search_suffix: str = "hiring talent recruiter HR",
    max_characters: int = 1500,
    backend: str = "auto",
) -> CandidateEvidence:
    """Run a targeted Exa search for a single candidate's hiring evidence.

    Uses the LinkedIn profile ID + name to surface pages that mention
    the person in a hiring context (HR/recruiter/talent pages, team
    directories, company career pages). Returns a ``CandidateEvidence``
    with the most relevant snippet for personalization.

    This is a *search* (not a contents fetch) — it finds pages *about*
    the candidate, not the candidate's own LinkedIn profile text. The
    goal is to discover evidence like "HR Manager at Apranga" or
    "Recruiter at LPP" that the outreach writer can reference.
    """
    profile_id = _profile_id_from_url(profile_url)
    if not profile_id:
        return CandidateEvidence(profile_url=profile_url)

    # Build a query targeting pages that mention this person + hiring context
    query_parts = [f"site:linkedin.com/in/{profile_id}"]
    if name.strip():
        clean_name = re.sub(r"[^\w\s]", "", name.strip())[:60]
        query_parts.insert(0, f'"{clean_name}"')
    query_parts.append(search_suffix)

    query = " ".join(query_parts)

    result = web_search(query, num_results=3, backend=backend)
    if result.error:
        return CandidateEvidence(
            profile_url=profile_url, source=backend, personalization_text=""
        )

    # Collect snippet text from all hits
    snippets: list[str] = []
    for hit in result.hits:
        text = (hit.snippet or "").strip()
        if text:
            snippets.append(text)
        title = (hit.title or "").strip()
        if title and title not in snippets:
            snippets.append(title)

    combined = " ".join(snippets)[:max_characters]
    return CandidateEvidence(
        profile_url=profile_url,
        personalization_text=combined,
        sourcing_keywords=query,
        source=result.backend or backend,
    )


def search_candidates_evidence_batch(
    candidates: list[dict[str, str]],
    *,
    search_suffix: str = "hiring talent recruiter",
    max_characters: int = 1500,
    backend: str = "auto",
) -> dict[str, CandidateEvidence]:
    """Run targeted evidence search for multiple candidates.

    ``candidates`` is a list of dicts with at least ``profile_url`` key
    (and optionally ``name``). Returns ``{profile_url: CandidateEvidence}``.

    Skips candidates where ``enriched_about`` already has enough text
    (meaning the standard /contents enrichment was sufficient).
    """
    results: dict[str, CandidateEvidence] = {}
    for candidate in candidates:
        url = (candidate.get("profile_url") or "").strip()
        name = (candidate.get("name") or "").strip()
        if not url:
            continue

        # Skip if already well-enriched by the standard /contents pipeline
        existing = (candidate.get("enriched_about") or "").strip()
        if len(existing) >= max_characters:
            continue

        evidence = search_candidate_evidence(
            url,
            name=name,
            search_suffix=search_suffix,
            max_characters=max_characters,
            backend=backend,
        )
        if evidence.personalization_text:
            results[url] = evidence

    return results
