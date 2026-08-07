"""Central discovery registry for pluggable opportunity sources.

New job portals can be added by defining a ``discover_*`` callable in the
``sources`` package (or a sibling module) and registering a
:class:`RegistrySource` entry here or in :mod:`sources.adapters` -- no core
orchestrator edits required. The orchestrator resolves each entry's discover
callable lazily from the ``sources`` package namespace, so runtime
monkeypatching of the public functions keeps working.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def source_block(config: dict[str, Any], key: str) -> dict[str, Any]:
    """Read a source block from the ``opportunities.sources`` config."""
    sources_cfg = (config.get("opportunities") or {}).get("sources") or {}
    block = sources_cfg.get(key) or {}
    return block if isinstance(block, dict) else {}


def block_enabled(block: dict[str, Any], default: bool = False) -> bool:
    return bool(block.get("enabled", default))


class RegistrySource:
    """Registry entry binding source metadata to a discover callable.

    The callable is looked up by *discover_name* in the ``sources`` package
    namespace at dispatch time (not bound at registration time).
    """

    def __init__(
        self,
        *,
        name: str,
        config_key: str,
        snapshot_type: str,
        discover_name: str,
        default_enabled: bool = False,
        multi: bool = False,
        enabled: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        self.name = name
        self.config_key = config_key
        self.snapshot_type = snapshot_type
        self.default_enabled = default_enabled
        self.discover_name = discover_name
        self.multi = multi
        self._enabled_fn = enabled

    def enabled(self, config: dict[str, Any]) -> bool:
        if self._enabled_fn is not None:
            return self._enabled_fn(config)
        return block_enabled(
            source_block(config, self.config_key), self.default_enabled
        )


SOURCE_ADAPTERS: list[RegistrySource] = []


def register(source: RegistrySource) -> RegistrySource:
    """Append *source* to the discovery registry (in registration order)."""
    SOURCE_ADAPTERS.append(source)
    return source
