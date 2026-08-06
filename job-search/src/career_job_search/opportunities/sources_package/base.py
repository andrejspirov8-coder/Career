"""Base data structures and helper utilities for opportunity source adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from career_job_search.opportunities.models import Opportunity

@dataclass
class SourceResult:
    source: str
    status: str
    snapshot_type: str
    item_count: int
    duration_ms: int
    complete: bool
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "snapshot_type": self.snapshot_type,
            "item_count": self.item_count,
            "duration_ms": self.duration_ms,
            "complete": self.complete,
            "error": self.error,
        }

@dataclass
class DiscoveryBatch:
    opportunities: list[Opportunity] = field(default_factory=list)
    source_results: list[SourceResult] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        return any(result.status == "failed" for result in self.source_results)

@dataclass
class SourceDiscovery:
    opportunities: list[Opportunity] = field(default_factory=list)
    complete: bool = True
    status: str | None = None
    note: str = ""
