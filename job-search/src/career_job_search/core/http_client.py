"""Async HTTP client with retry and exponential backoff.

Replaces raw ``urllib.request.urlopen`` calls with httpx AsyncClient
features:

- 3 retries on 429/503 with exponential backoff (1s, 2s, 4s)
- Configurable timeout per request
- Proper resource cleanup via context manager
- Thread-safe via httpx's internal locking

Designed for OpenClaw code editing best practices:
- DRY: single retry implementation used by all source fetchers
- YAGNI: only handles transient failures, not business logic
- Clean code: simple sync + async entry points
- Automated testing: ``fetch_with_retry`` is easily mockable
"""

from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_TIMEOUT = 15  # seconds


class FetchError(Exception):
    """Raised when all retries are exhausted."""

    def __init__(self, url: str, status: int | None, reason: str):
        self.url = url
        self.status = status
        self.reason = reason
        super().__init__(f"{reason} ({url}, status={status})")


async def fetch_text_with_retry(
    url: str,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    timeout: int = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
) -> str:
    """Fetch URL text with retry. Returns body on success.

    Raises ``FetchError`` after exhausting retries.
    """
    last_exc: Exception | None = None
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        headers=headers
        or {
            "User-Agent": "career-job-search/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )

    try:
        for attempt in range(max_retries):
            try:
                resp = await client.get(url)
                status = resp.status_code

                if status == 200:
                    return resp.text

                if status in {429, 503, 502, 504}:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "%s retry %d/%d after HTTP %d — waiting %.1fs",
                        url,
                        attempt + 1,
                        max_retries,
                        status,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable status (404, 403, etc.)
                last_exc = FetchError(url, status, f"HTTP {status}")
                break

            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "%s timeout on attempt %d/%d — waiting %.1fs",
                    url,
                    attempt + 1,
                    max_retries,
                    delay,
                )
                await asyncio.sleep(delay)
                last_exc = exc

    finally:
        await client.aclose()

    raise FetchError(
        url,
        getattr(last_exc, "status", None),
        str(last_exc or "all retries exhausted"),
    )


def fetch_text_sync(
    url: str,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    timeout: int = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
) -> str:
    """Synchronous wrapper around ``fetch_text_with_retry``.

    Use only when async is not available (e.g. standalone scripts,
    orchestrator entry points that don't use async/await).
    """
    return asyncio.run(
        fetch_text_with_retry(
            url,
            max_retries=max_retries,
            base_delay=base_delay,
            timeout=timeout,
            headers=headers,
        )
    )


async def fetch_status_and_text(
    url: str,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    timeout: int = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Return ``(status_code, text_body)`` with retry."""
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        headers=headers
        or {
            "User-Agent": "career-job-search/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    last_exc: Exception | None = None
    try:
        for attempt in range(max_retries):
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return 200, resp.text
                if resp.status_code in {429, 503, 502, 504}:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "%s HTTP %d on attempt %d/%d — retrying",
                        url,
                        resp.status_code,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                return resp.status_code, resp.text
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "%s timeout on attempt %d/%d — retrying",
                    url,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(delay)
                last_exc = exc
    finally:
        await client.aclose()
    if last_exc:
        return 0, f"all retries exhausted after {max_retries} attempts: {last_exc}"
    return 0, f"all retries exhausted after {max_retries} attempts"
