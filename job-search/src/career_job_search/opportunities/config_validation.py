"""Pydantic-powered validation for opportunity discovery configuration.

Validates the YAML config at load time so that errors like
``base_url must include a search path`` or ``queries must be a list``
are caught early with structured error messages, including the source
and field path for debugging.

Designed for OpenClaw code editing best practices:
- DRY: single source of truth for field validation
- YAGNI: only validates fields currently used by sources.py
- Clean code: typed models with clear error messages
- Automated testing: canonicalise_opportunities_config() is easy to unit-test
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# Patterns and defaults borrowed from sources.py so validation mirrors runtime.
_DEFAULT_LIVE_TIMEOUT_SECONDS = 6
_DEFAULT_FETCH_TIMEOUT_SECONDS = 30

# Source name aliases: map shorthand names to canonical names
_SOURCE_ALIASES = {
    "uzt": "uzt_open_data",
    "work_in_lithuania": "workinlithuania_public_search",
}

# Field aliases within sources: map shorthand field names to canonical names
_FIELD_ALIASES = {
    "cvmarket_rss": {"rss_url": "feed_url"},
}


# ---------------------------------------------------------------------------
# Source config models
# ---------------------------------------------------------------------------


class CVOnlineConfig(BaseModel):
    """CVOnline (https://www.cvonline.lt/) public search config."""

    model_config = {"extra": "forbid"}

    enabled: bool = False
    base_url: str = "https://www.cvonline.lt/lt/search"
    queries: list[str] = Field(default_factory=list, min_length=0)
    max_results_per_query: int = Field(default=50, ge=1, le=200)
    max_queries: int = Field(default=10, ge=1)
    network_timeout_seconds: int = Field(default=30, ge=1)
    depth: int = Field(default=1, ge=0, le=3)

    @field_validator("queries", mode="before")
    @classmethod
    def reject_non_list_queries(cls, value: Any) -> Any:
        """Pre-coercion check: reject string values for queries fields."""
        if isinstance(value, str):
            raise ValueError(
                "queries must be a list of search terms, not a string. "
                "Example: ['Director Operations'] instead of 'Director Operations'."
            )
        return value

    @field_validator("queries")
    @classmethod
    def queries_must_be_non_empty_when_enabled(cls, value: list[str], info: Any) -> list[str]:
        enabled = info.data.get("enabled", False)
        if enabled and (not value or not any(v.strip() for v in value)):
            raise ValueError("'queries' must be a non-empty list of search terms when enabled.")
        for i, item in enumerate(value):
            if not isinstance(item, str):
                raise ValueError(f"queries[{i}] must be a string, got {type(item).__name__}.")
            if item.strip() == "":
                raise ValueError(f"queries[{i}] must not be empty.")
        return value

    @field_validator("base_url")
    @classmethod
    def base_url_must_include_search_path(cls, value: str) -> str:
        if not value:
            raise ValueError("base_url must not be empty.")
        if "/search" not in value:
            raise ValueError(
                f"base_url must include a search path (e.g. /search or /lt/search); got '{value}'."
            )
        return value.strip()


class CVBankasConfig(BaseModel):
    """CVBankas (https://www.cvbankas.lt/) public search config."""

    model_config = {"extra": "forbid"}

    enabled: bool = False
    base_url: str = "https://www.cvbankas.lt/"
    queries: list[str] = Field(default_factory=list, min_length=0)
    location_ids: list[int] = Field(default_factory=lambda: [606, 502])
    max_results_per_query: int = Field(default=50, ge=1, le=200)
    max_queries: int = Field(default=10, ge=1)
    network_timeout_seconds: int = Field(default=30, ge=1)

    @model_validator(mode="before")
    @classmethod
    def reject_non_list_queries(cls, data: Any) -> Any:
        """Pre-coercion check: reject string values for queries fields."""
        if isinstance(data, dict):
            queries = data.get("queries")
            if isinstance(queries, str):
                raise ValueError(
                    "'queries' must be a list of search terms, not a string. "
                    "Example: ['Manager'] instead of 'Manager'."
                )
        return data


class UzTConfig(BaseModel):
    """UŽT (Užimtumo tarnyba) public API config."""

    model_config = {"extra": "forbid"}

    enabled: bool = False
    feed_url: str = "https://uzt.gov.lt/api/v1/job-vacancies"
    api_url: str = "https://get.data.gov.lt/datasets/gov/uzt/ldv/Vieta"
    municipality: str = ""
    max_records: int = Field(default=300, ge=1)
    network_timeout_seconds: int = Field(default=30, ge=1)
    live_fallback_enabled: bool = False
    live_fallback_url: str = ""
    live_fallback_max_records: int = Field(default=20, ge=1)
    live_fallback_area_ids: list[int] = Field(default_factory=list)
    max_feed_age_days: int = Field(default=7, ge=1)


class CVMarketConfig(BaseModel):
    """CVMarket RSS feed config."""

    model_config = {"extra": "forbid"}

    enabled: bool = False
    feed_url: str = "https://www.cvmarket.lt/rss-listings.xml"
    network_timeout_seconds: int = Field(default=30, ge=1)
    rate_limit_seconds: float = Field(default=1.0, ge=0.1)
    locations: list[str] = Field(default_factory=list)
    max_items: int = Field(default=100, ge=1)
    max_feed_age_hours: int = Field(default=24, ge=1)


class WorkInLithuaniaConfig(BaseModel):
    """WorkInLithuania (https://workinelithuania.gov.lt/) vacancy scanner."""

    model_config = {"extra": "forbid"}

    enabled: bool = False
    api_url: str = "https://workinelithuania.com/api"
    base_url: str = "https://workinelithuania.com"
    search_page_url_template: str = "https://workinelithuania.com/jobs/{query}"
    city_ids: list[int] = Field(default_factory=list)
    max_pages: int = Field(default=10, ge=1)
    max_records: int = Field(default=100, ge=1)
    network_timeout_seconds: int = Field(default=30, ge=1)
    rate_limit_seconds: float = Field(default=1.0, ge=0.1)


class LinkedInConfig(BaseModel):
    """LinkedIn job discovery config."""

    model_config = {"extra": "forbid"}

    enabled: bool = False
    mode: str = "local_profile"
    base_url: str = "https://www.linkedin.com"
    location: str = ""
    posted_within_hours: int = Field(default=72, ge=1)
    max_queries: int = Field(default=5, ge=1)
    max_results_per_query: int = Field(default=10, ge=1)
    max_jobs: int = Field(default=50, ge=1)
    pages: int = Field(default=1, ge=1)
    max_detail_pages: int = Field(default=10, ge=1)
    timeout_ms: int = Field(default=30000, ge=1000)
    settle_ms: int = Field(default=1000, ge=100)
    browser_channel: str = "chrome"
    headed: bool = False
    profile_dir: str = ""
    queries: list[str] = Field(default_factory=list)
    queries_by_variant: dict[str, list[str]] = Field(default_factory=dict)
    browser: dict[str, Any] = Field(default_factory=dict)

    @field_validator("mode")
    @classmethod
    def mode_must_be_valid(cls, value: str) -> str:
        valid = {"local_profile", "connected_chrome", "chrome_session", "external_browser"}
        if value.casefold() not in valid:
            raise ValueError(f"mode must be one of {valid}, got '{value}'.")
        return value


class JobBoardConfig(BaseModel):
    """Job board link list (manual review links)."""

    model_config = {"extra": "forbid"}

    enabled: bool = False
    links: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("links")
    @classmethod
    def links_must_be_objects_not_strings(cls, value: list[Any]) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise ValueError("'links' must be a list.")
        for i, item in enumerate(value):
            if not isinstance(item, dict):
                raise ValueError(
                    f"links[{i}] must be an object with 'title' and 'url' keys, not a string."
                )
        return value

    @field_validator("links", mode="before")
    @classmethod
    def reject_string_links(cls, value: Any) -> Any:
        """Reject plain strings in links before Pydantic tries to coerce them."""
        if isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, str):
                    raise ValueError(
                        f"links[{i}] must be an object with 'title' and 'url' keys, not a plain string."
                    )
        return value


class WebSearchConfig(BaseModel):
    """Web search link list (manual review links)."""

    model_config = {"extra": "forbid"}

    enabled: bool = False
    links: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("links")
    @classmethod
    def links_must_be_objects_not_strings(cls, value: list[Any]) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise ValueError("'links' must be a list.")
        for i, item in enumerate(value):
            if not isinstance(item, dict):
                raise ValueError(
                    f"links[{i}] must be an object with 'title' and 'url' keys, not a string."
                )
        return value


class InboxConfig(BaseModel):
    """Manual inbox job entries."""

    model_config = {"extra": "forbid"}

    enabled: bool = True
    path: str = "inbox/jobs"
    exclude_name_patterns: list[str] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def path_must_be_relative_or_absolute(cls, value: str) -> str:
        if not value or not str(value).strip():
            raise ValueError("path must not be empty.")
        return value


class ATSConfig(BaseModel):
    """ATS provider configuration."""

    model_config = {"extra": "forbid"}

    enabled: bool = False
    network_timeout_seconds: int = Field(default=30, ge=1)
    rate_limit_seconds: float = Field(default=1.0, ge=0.1)
    providers: list[dict[str, Any]] = Field(default_factory=list)
    fixtures: list[dict[str, Any]] = Field(default_factory=list)


class CompanyWatchlistConfig(BaseModel):
    """Company watchlist source."""

    model_config = {"extra": "forbid"}

    enabled: bool = False
    companies: list[dict[str, Any]] = Field(default_factory=list)


class OfficialCompanyCareersConfig(BaseModel):
    """Official company careers scraper."""

    model_config = {"extra": "forbid"}

    enabled: bool = False
    companies: list[dict[str, Any]] = Field(default_factory=list)
    network_timeout_seconds: int = Field(default=30, ge=1)
    max_page_chars: int = Field(default=100000, ge=1000)
    max_rows_per_company: int = Field(default=100, ge=1)


# ---------------------------------------------------------------------------
# Top-level config model
# ---------------------------------------------------------------------------


class OpportunitiesConfig(BaseModel):
    """Validated opportunity discovery configuration."""

    model_config = {"extra": "forbid"}

    # --- sources ---
    inbox: InboxConfig = Field(default_factory=InboxConfig)
    ats: ATSConfig = Field(default_factory=ATSConfig)
    company_watchlist: CompanyWatchlistConfig = Field(default_factory=CompanyWatchlistConfig)
    linkedin: LinkedInConfig = Field(default_factory=LinkedInConfig)
    job_board: JobBoardConfig = Field(default_factory=JobBoardConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    cvmarket_rss: CVMarketConfig = Field(default_factory=CVMarketConfig)
    cvonline_public_search: CVOnlineConfig = Field(default_factory=CVOnlineConfig)
    cvbankas_public_search: CVBankasConfig = Field(default_factory=CVBankasConfig)
    uzt_open_data: UzTConfig = Field(default_factory=UzTConfig)
    workinlithuania_public_search: WorkInLithuaniaConfig = Field(
        default_factory=WorkInLithuaniaConfig
    )
    official_company_careers: OfficialCompanyCareersConfig = Field(
        default_factory=OfficialCompanyCareersConfig
    )

    # --- scoring and geography ---
    scoring: dict[str, Any] = Field(default_factory=dict)
    geography: dict[str, Any] = Field(default_factory=dict)
    liveness: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _format_validation_error(exc: Exception, context_path: str = "") -> str:
    """Format a Pydantic ValidationError into a human-readable path-aware message.

    Extracts the field path and error detail from Pydantic errors.
    """
    import json
    from pydantic_core import ValidationError

    if not isinstance(exc, ValidationError):
        return str(exc)

    # Build a readable message from Pydantic validation errors
    messages: list[str] = []
    for error in exc.errors():
        # error is a dict with keys: 'type', 'loc', 'msg', 'input', ...
        loc = error.get("loc", ())
        msg = error.get("msg", "validation failed")

        # Build the full path: source.field1.field2
        if loc:
            path = ".".join(str(p) for p in loc)
        else:
            path = context_path or "config"

        messages.append(f"{path}: {msg}")

    return "; ".join(messages) if messages else str(exc)


def canonicalise_opportunities_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Canonicalise and validate the raw config dict.

    - Applies source aliases (uzt → uzt_open_data, work_in_lithuania → workinlithuania_public_search)
    - Applies field aliases (rss_url → feed_url in cvmarket_rss)
    - Rejects collisions (both aliased and canonical names present)
    - Validates all nested fields with path-aware error messages
    - Returns the canonical dict suitable for runtime use

    Raises ``ValueError`` with path information (e.g., "cvonline_public_search.queries")
    so that configuration errors are easy to locate and fix.
    """
    # Extract sources from nested or flat layout
    if "opportunities" in raw:
        sources_dict = (raw.get("opportunities") or {}).get("sources") or {}
    else:
        sources_dict = raw

    if not isinstance(sources_dict, dict):
        sources_dict = {}

    # Apply source aliases and detect collisions
    canonical_sources: dict[str, dict[str, Any]] = {}
    for source_name, source_block in sources_dict.items():
        canonical_name = _SOURCE_ALIASES.get(source_name, source_name)

        # Check for collision: both aliased and canonical names present
        if canonical_name != source_name and canonical_name in sources_dict:
            raise ValueError(
                f"Source alias collision: cannot have both '{source_name}' and '{canonical_name}' "
                f"in the same config. Use the canonical name '{canonical_name}' only."
            )

        if not isinstance(source_block, dict):
            source_block = {}

        # Apply field aliases within this source and detect field collisions
        aliased_block = dict(source_block)
        if source_name in _FIELD_ALIASES or canonical_name in _FIELD_ALIASES:
            field_map = _FIELD_ALIASES.get(source_name) or _FIELD_ALIASES.get(canonical_name) or {}
            for alias_name, canonical_field_name in field_map.items():
                if alias_name in aliased_block and canonical_field_name in aliased_block:
                    raise ValueError(
                        f"Field alias collision in '{canonical_name}': "
                        f"cannot have both '{alias_name}' and '{canonical_field_name}'. "
                        f"Use the canonical name '{canonical_field_name}' only."
                    )
                if alias_name in aliased_block:
                    aliased_block[canonical_field_name] = aliased_block.pop(alias_name)

        canonical_sources[canonical_name] = aliased_block

    # Validate using Pydantic models with path-aware error context
    payload = {**canonical_sources}
    extra_keys = {k: v for k, v in raw.items() if k not in {"opportunities"}}
    payload.update(extra_keys)

    try:
        validated = OpportunitiesConfig.model_validate(payload)
        return {
            "opportunities": {
                "sources": validated.model_dump(exclude_unset=False, exclude_defaults=False),
                **{k: v for k, v in payload.items() if k not in canonical_sources},
            }
        }
    except Exception as exc:
        error_msg = _format_validation_error(exc)
        raise ValueError(error_msg) from exc


def load_and_validate_config(path: str | None) -> dict[str, Any]:
    """Load YAML from *path*, canonicalise, and validate it.

    Used by orchestrator.py ``load_config`` as a drop-in replacement.
    Returns the raw dict (not an OpportunitiesConfig object) so callers
    can continue working with dictionaries.

    Args:
        path: Path to opportunities.yaml, or None for inbox-only defaults

    Returns:
        dict with ``opportunities.sources`` and any top-level scoring/geography/liveness

    Raises:
        FileNotFoundError if path is provided but file does not exist
        ValueError if config validation fails or YAML parsing fails
    """
    import yaml

    if path is None:
        # Inbox-only default with absolute path resolution
        from career_job_search.core.paths import project_path

        return {
            "opportunities": {
                "sources": {
                    "inbox": {
                        "enabled": True,
                        "path": str(project_path("inbox", "jobs")),
                    }
                }
            }
        }

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Opportunity config not found: {p}")

    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse YAML from {p}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Opportunity config must be a mapping (dict), not a list or string.")

    # Canonicalise and validate
    return canonicalise_opportunities_config(data)


def validate_opportunities_config(raw: dict[str, Any]) -> OpportunitiesConfig:
    """Validate and return an OpportunitiesConfig from a raw dict.

    Legacy function for backwards compatibility. Use canonicalise_opportunities_config
    for new code.

    Raises ``ValueError`` with a structured message on any invalid field.
    """
    canonical = canonicalise_opportunities_config(raw)
    sources = (canonical.get("opportunities") or {}).get("sources") or {}
    extra = {k: v for k, v in canonical.items() if k != "opportunities"}

    payload = {**sources, **extra}
    return OpportunitiesConfig.model_validate(payload)


def suggest_source_fixes(raw: dict[str, Any]) -> list[str]:
    """Return human-readable suggestions for common config errors.

    Useful for displaying guidance when a source returns ``status=failed``.
    """
    suggestions: list[str] = []

    sources_to_check = {
        "cvonline_public_search": CVOnlineConfig,
        "cvbankas_public_search": CVBankasConfig,
        "uzt_open_data": UzTConfig,
        "cvmarket_rss": CVMarketConfig,
        "workinlithuania_public_search": WorkInLithuaniaConfig,
        "linkedin": LinkedInConfig,
    }

    sources_block = (raw.get("opportunities") or {}).get("sources") or {}

    for source_name, model_cls in sources_to_check.items():
        config_block = sources_block.get(source_name, {})
        if not config_block:
            continue

        enabled = config_block.get("enabled", False)
        if not enabled:
            continue

        # Quick checks without full validation
        if source_name == "cvonline_public_search":
            base_url = config_block.get("base_url", "")
            if "/search" not in str(base_url):
                suggestions.append(
                    "cvonline_public_search: base_url must include '/search' "
                    "(e.g. https://www.cvonline.lt/lt/search)"
                )
            queries = config_block.get("queries")
            if not isinstance(queries, list) or not queries:
                suggestions.append(
                    "cvonline_public_search: 'queries' must be a non-empty list "
                    "of search terms (not a single string)."
                )

        elif source_name == "cvbankas_public_search":
            queries = config_block.get("queries")
            if not isinstance(queries, list) or not queries:
                suggestions.append(
                    "cvbankas_public_search: 'queries' must be a non-empty list "
                    "of search terms."
                )

        elif source_name == "linkedin":
            mode = str(config_block.get("mode", "local_profile")).casefold()
            if mode == "local_profile":
                suggestions.append(
                    "linkedin: 'local_profile' mode hits LinkedIn's authwall. "
                    "Switch to 'connected_chrome' and keep Chrome logged in."
                )

        elif source_name == "uzt_open_data":
            api_url = config_block.get("api_url", "")
            if "uzt.gov.lt" in str(api_url):
                suggestions.append(
                    "uzt_open_data: DNS resolution for uzt.gov.lt may fail. "
                    "Use 'https://get.data.gov.lt/datasets/gov/uzt/ldv/Vieta'."
                )

    # job_board and web_search: check that links are dicts
    for board_name in ("job_board", "web_search"):
        links = sources_block.get(board_name, {}).get("links")
        if links and isinstance(links, list):
            for i, link in enumerate(links):
                if not isinstance(link, dict):
                    suggestions.append(
                        f"{board_name}.links[{i}] must be an object with 'title' "
                        "and 'url' keys (not a plain string)."
                    )

    return suggestions
