"""Base data structures and the source-adapter contract for opportunity sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

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


class SourceAdapter(Protocol):
    """Contract for a pluggable opportunity source.

    Implementations expose discovery metadata plus a ``discover`` method that
    returns a :class:`SourceDiscovery`. Multi-result sources (for example the
    ATS board, which produces one result per configured provider) additionally
    expose ``discover_each`` returning a list of ``(source_name, discovery)``
    tuples, where each item may be a raised exception for per-item isolation.
    """

    name: str
    config_key: str
    snapshot_type: str
    default_enabled: bool

    def discover(
        self, config: dict[str, Any], *, now: datetime | None = None
    ) -> SourceDiscovery: ...

    def discover_each(
        self, config: dict[str, Any], *, now: datetime | None = None
    ) -> list[tuple[str, SourceDiscovery | BaseException]]: ...
