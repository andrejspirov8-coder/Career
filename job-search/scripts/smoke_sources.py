"""Headless opportunity source-discovery smoke (CI).

Exercises the modular source registry end-to-end without a browser or
credentials: every registered adapter must resolve a discover callable, a
fully-disabled config must yield an empty complete batch, and an enabled
offline source must dispatch gracefully.
"""

from __future__ import annotations

import career_job_search.opportunities.sources as _sources
from career_job_search.opportunities.sources import (
    SOURCE_ADAPTERS,
    discover_opportunities_with_results,
)


def _config(**source_blocks: object) -> dict[str, object]:
    return {"opportunities": {"sources": dict(source_blocks)}}


def main() -> int:
    for adapter in SOURCE_ADAPTERS:
        if not callable(getattr(_sources, adapter.discover_name, None)):
            raise SystemExit(
                f"registry broken: {adapter.discover_name!r} not in sources namespace"
            )

    batch = discover_opportunities_with_results(_config(inbox={"enabled": False}))
    assert not batch.partial, [r.to_dict() for r in batch.source_results]
    assert batch.opportunities == []
    assert batch.source_results == []

    batch = discover_opportunities_with_results(
        _config(inbox={"enabled": False}, company_watchlist={"enabled": True})
    )
    assert not batch.partial, [r.to_dict() for r in batch.source_results]
    results = {r.source: r for r in batch.source_results}
    assert results["company_watchlist"].status == "monitor_only"

    print(f"source smoke ok: {len(SOURCE_ADAPTERS)} adapters, empty+complete batch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
