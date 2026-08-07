"""Registered opportunity source adapters (the discovery registry).

Order matters: adapters are dispatched in registration order, which matches
the historical ``discover_opportunities_with_results`` sequence.
"""

from __future__ import annotations

from career_job_search.opportunities.sources.registry import (
    RegistrySource,
    block_enabled,
    register,
    source_block,
)

_LINKEDIN_MANAGED_MODES = frozenset(
    {"connected_chrome", "chrome_session", "external_browser"}
)


def _linkedin_enabled(config: dict[str, object]) -> bool:
    block = source_block(config, "linkedin")
    if not block_enabled(block, default=False):
        return False
    mode = str(block.get("mode") or "local_profile").strip().casefold()
    return mode not in _LINKEDIN_MANAGED_MODES


SOURCE_ADAPTERS: list[RegistrySource] = [
    register(
        RegistrySource(
            name="inbox",
            config_key="inbox",
            snapshot_type="snapshot",
            discover_name="_discover_inbox",
            default_enabled=True,
        )
    ),
    register(
        RegistrySource(
            name="company_watchlist",
            config_key="company_watchlist",
            snapshot_type="snapshot",
            discover_name="_discover_watchlist",
        )
    ),
    register(
        RegistrySource(
            name="ats",
            config_key="ats",
            snapshot_type="snapshot",
            discover_name="_discover_ats_each",
            multi=True,
        )
    ),
    register(
        RegistrySource(
            name="linkedin",
            config_key="linkedin",
            snapshot_type="snapshot",
            discover_name="_discover_linkedin",
            enabled=_linkedin_enabled,
        )
    ),
    register(
        RegistrySource(
            name="job_board",
            config_key="job_board",
            snapshot_type="snapshot",
            discover_name="_discover_job_board",
        )
    ),
    register(
        RegistrySource(
            name="web_search",
            config_key="web_search",
            snapshot_type="snapshot",
            discover_name="_discover_web_search",
        )
    ),
    register(
        RegistrySource(
            name="cvmarket",
            config_key="cvmarket_rss",
            snapshot_type="incremental",
            discover_name="discover_cvmarket_rss",
        )
    ),
    register(
        RegistrySource(
            name="cvonline",
            config_key="cvonline_public_search",
            snapshot_type="incremental",
            discover_name="discover_cvonline_public_search",
        )
    ),
    register(
        RegistrySource(
            name="cvbankas",
            config_key="cvbankas_public_search",
            snapshot_type="incremental",
            discover_name="discover_cvbankas_public_search",
        )
    ),
    register(
        RegistrySource(
            name="workinlithuania",
            config_key="workinlithuania_public_search",
            snapshot_type="snapshot",
            discover_name="discover_workinlithuania_public_search",
        )
    ),
    register(
        RegistrySource(
            name="uzt_open_data",
            config_key="uzt_open_data",
            snapshot_type="incremental",
            discover_name="discover_uzt_open_data",
        )
    ),
    register(
        RegistrySource(
            name="official_company_careers",
            config_key="official_company_careers",
            snapshot_type="snapshot",
            discover_name="_discover_company_careers_each",
            multi=True,
        )
    ),
]
