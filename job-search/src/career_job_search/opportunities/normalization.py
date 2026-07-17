"""Canonical parsing shared by all opportunity ingestion adapters."""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urlsplit

_LINKEDIN_JOB_ID_RE = re.compile(r"/jobs/view/(\d+)", re.IGNORECASE)


def linkedin_job_id_from_url(url: str) -> str:
    match = _LINKEDIN_JOB_ID_RE.search(url or "")
    return match.group(1) if match else ""


def canonical_linkedin_job_url(
    url: str,
    *,
    normalize_url: Callable[[str], str],
    require_linkedin_host: bool = True,
) -> str:
    """Remove tracking and validate a LinkedIn job URL."""

    normalized = normalize_url(url)
    if not linkedin_job_id_from_url(normalized):
        return ""
    if require_linkedin_host:
        host = urlsplit(normalized).netloc.casefold()
        if host != "linkedin.com" and not host.endswith(".linkedin.com"):
            return ""
    return normalized


def infer_remote_policy(text: str) -> str:
    """Return the normalized work-location mode found in free text."""

    lowered = (text or "").casefold()
    if "hybrid" in lowered or "hibrid" in lowered:
        return "hybrid"
    if any(
        token in lowered
        for token in ("remote", "nuotol", "work from home", "wfh")
    ):
        return "remote"
    if any(token in lowered for token in ("on-site", "onsite", "on site")):
        return "onsite"
    return ""
