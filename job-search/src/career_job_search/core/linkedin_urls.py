"""LinkedIn URL canonicalization utilities.

All public functions return canonical URLs **without** a trailing slash for
consistent string comparison across the codebase.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

LINKEDIN_PROFILE_RE = re.compile(r"linkedin\.com/in/([^/\?#]+)", re.IGNORECASE)
LINKEDIN_JOB_ID_RE = re.compile(r"/jobs/view/(\d+)", re.IGNORECASE)

_SKIP_PROFILE_SLUGS = frozenset({"company", "school", "showcase", "pub", "learning"})


def _normalise_url(url: str) -> str:
    """Strip query params, fragment, enforce https, lowercase host, strip trailing slash."""
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if not parsed.scheme:
        parsed = urlsplit("https://" + raw.lstrip("/"))
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", host, path, "", ""))


def canonical_linkedin_url(url: str, *, url_type: str = "profile") -> str:
    """Canonicalize a LinkedIn URL for the given type ('profile' | 'job')."""
    if url_type == "profile":
        return canonical_linkedin_profile_url(url)
    if url_type == "job":
        return canonical_linkedin_job_url(url)
    raise ValueError(f"Unknown url_type: {url_type!r}")


def canonical_linkedin_profile_url(url: str) -> str:
    """Return canonical LinkedIn profile URL or empty string.

    Returns URL **with** trailing slash for backward compatibility
    with existing dict-key usage throughout the codebase.
    """
    raw = (url or "").strip()
    if not raw or "/in/" not in raw.casefold():
        return ""
    parsed = urlsplit(raw if "://" in raw else "https://" + raw.lstrip("/"))
    segments = [s for s in parsed.path.split("/") if s]
    if len(segments) < 2 or segments[0].casefold() != "in":
        return ""
    slug = segments[1]
    if slug.casefold() in _SKIP_PROFILE_SLUGS:
        return ""
    return f"https://www.linkedin.com/in/{slug}/"


def canonical_linkedin_job_url(
    url: str,
    *,
    normalize_url: Callable[[str], str] | None = None,
    require_linkedin_host: bool = True,
) -> str:
    """Return canonical LinkedIn job URL or empty string."""
    normalizer = normalize_url or _normalise_url
    normalized = normalizer(url)
    if not linkedin_job_id(normalized):
        return ""
    if require_linkedin_host:
        host = urlsplit(normalized).netloc.casefold()
        if host != "linkedin.com" and not host.endswith(".linkedin.com"):
            return ""
    return normalized


def linkedin_profile_id(url: str) -> str | None:
    """Extract the profile slug (e.g. ``andrej-spirov``) from a LinkedIn URL."""
    m = LINKEDIN_PROFILE_RE.search(url or "")
    return m.group(1) if m else None


def linkedin_job_id(url: str) -> str | None:
    """Extract the numeric job ID from a LinkedIn ``/jobs/view/{id}`` URL."""
    m = LINKEDIN_JOB_ID_RE.search(url or "")
    return m.group(1) if m else None
