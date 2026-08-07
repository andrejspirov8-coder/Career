"""Source error classification and alert generation.

Maps raw source failure reasons to human-readable severity levels
and suggested remediation actions.  Prevents the ``status=failed``
ambiguity by always returning a structured alert.

Designed for OpenClaw code editing best practices:
- DRY: single classification dictionary, used by orchestrator + dashboard
- Clean code: clear severity tiers with actionable messages
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceAlert:
    source: str
    severity: str  # "critical", "high", "medium", "low"
    message: str
    action: str  # what the operator should do


# Mapping from error substrings → (severity, message, action).
# Order matters: more specific patterns first.
ERROR_PATTERNS: list[tuple[str, str, str, str]] = [
    # Auth/access issues
    (
        "authwall",
        "critical",
        "LinkedIn access blocked — authwall detected",
        "Open Chrome with LinkedIn logged in; use 'connected_chrome' mode.",
    ),
    (
        "captcha",
        "critical",
        "CAPTCHA triggered — source is rate-limiting or blocking bots",
        "Reduce request frequency; add rate_limit_seconds to config; consider switching to connected_chrome.",
    ),
    (
        "access denied",
        "high",
        "Page returned access denied",
        "Verify URL; check if the site requires authentication.",
    ),
    (
        "forbidden",
        "high",
        "Page returned HTTP 403 Forbidden",
        "Check if the URL changed or requires headers/cookies.",
    ),
    # DNS/network
    (
        "getaddrinfo",
        "high",
        "DNS resolution failed for host",
        "Check network connectivity; verify the host is reachable.",
    ),
    (
        "ENOTFOUND",
        "high",
        "DNS resolution failed — host not found",
        "Check network connectivity; verify the URL in config.",
    ),
    (
        "connection refused",
        "medium",
        "Connection refused by remote host",
        "Check if the service is running or if the URL changed.",
    ),
    (
        "connection timeout",
        "medium",
        "Connection timed out",
        "Check network; increase network_timeout_seconds in config.",
    ),
    (
        "read timeout",
        "medium",
        "Request timed out reading response",
        "Increase network_timeout_seconds or reduce concurrent requests.",
    ),
    # HTTP status
    (
        "429",
        "high",
        "HTTP 429 Too Many Requests — rate limit hit",
        "Add rate_limit_seconds to source config; reduce max_results_per_query.",
    ),
    (
        "403",
        "medium",
        "HTTP 403 Forbidden — access denied",
        "Verify URL; check if the site changed its access policy.",
    ),
    (
        "404",
        "low",
        "HTTP 404 Not Found — page removed or moved",
        "Update source URL or disable this source.",
    ),
    (
        "502",
        "medium",
        "HTTP 502 Bad Gateway — upstream error",
        "Retry later; may be temporary.",
    ),
    (
        "503",
        "medium",
        "HTTP 503 Service Unavailable — temporary outage",
        "Retry later; may be temporary.",
    ),
    (
        "500",
        "medium",
        "HTTP 500 Internal Server Error — upstream error",
        "Retry later; may be temporary.",
    ),
    # Empty/empty results
    (
        "empty",
        "low",
        "Source returned zero results",
        "Verify the source is available; try adjusting search terms.",
    ),
    (
        "no results",
        "low",
        "Source returned no matching results",
        "Review search keywords; adjust config if source content changed.",
    ),
    # LinkedIn specific
    (
        "linkedin",
        "critical",
        "LinkedIn automation failed",
        "Ensure Chrome is running with LinkedIn logged in; check mode setting.",
    ),
    # DOM/selectors
    (
        "selector",
        "high",
        "CSS selector failed to find elements on page",
        "Source page layout may have changed — inspect and update selectors.",
    ),
    (
        "xpath",
        "high",
        "XPath expression failed to find elements on page",
        "Source page layout may have changed — inspect and update selectors.",
    ),
    # Playwright/Browser
    (
        "playwright",
        "critical",
        "Playwright browser automation failed",
        "Check if Chrome/Chromium is installed and accessible.",
    ),
    (
        "browser",
        "critical",
        "Browser session failed",
        "Check if a valid browser executable is configured.",
    ),
]


def classify_source_result(result: dict[str, Any]) -> SourceAlert | None:
    """Classify a single source result dict into a ``SourceAlert``.

    Returns ``None`` for successful results.
    """
    status = str(result.get("status") or "").lower().strip()
    error = str(result.get("error") or "").strip().lower()
    source = str(result.get("source") or "unknown")

    if status in {"success", "empty", "partial"}:
        return None  # No issue to flag

    # Critical path: source marked as failed
    if status == "failed":
        for pattern, severity, message, action in ERROR_PATTERNS:
            if pattern in error:
                alert = SourceAlert(source, severity, message, action)
                logger.info("Source alert [%s]: %s — %s", severity, message, action)
                return alert

    # If there's no error text but status is failed, create a generic alert
    return SourceAlert(
        source,
        "medium",
        f"Source '{source}' failed with status={status}",
        "Review logs for details; check if the source is available.",
    )


def classify_all_results(
    source_results: list[dict[str, Any]],
) -> list[SourceAlert]:
    """Classify all source results and return alerts for failed sources."""
    return [
        alert
        for result in source_results
        if (alert := classify_source_result(result)) is not None
    ]


def generate_summary_text(alerts: list[SourceAlert]) -> str:
    """Generate a short human-readable summary of source alerts.

    Useful for embedding in heartbeat messages or notification bodies.
    """
    if not alerts:
        return ""

    parts: list[str] = []
    for alert in alerts:
        severity_label = alert.severity.upper()
        parts.append(f"[{severity_label}] {alert.source}: {alert.message}")

    return "\n".join(parts)
