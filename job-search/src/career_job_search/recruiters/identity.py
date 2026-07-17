"""Recruiter identity normalization independent of policy and persistence."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def normalise_profile_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if not parsed.scheme:
        parsed = urlsplit("https://" + raw.lstrip("/"))
    host = (parsed.netloc or "www.linkedin.com").lower()
    if host == "linkedin.com":
        host = "www.linkedin.com"
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", host, path, "", ""))


def canonical_linkedin_profile_url(value: str) -> str:
    """Return a canonical LinkedIn `/in/` URL or an empty string."""

    raw = (value or "").strip()
    if not raw or "/in/" not in raw.casefold():
        return ""
    parsed = urlsplit(raw if "://" in raw else "https://" + raw.lstrip("/"))
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2 or segments[0].casefold() != "in":
        return ""
    slug = segments[1]
    if slug.casefold() in {"company", "school", "showcase", "pub", "learning"}:
        return ""
    return f"https://www.linkedin.com/in/{slug}/"
