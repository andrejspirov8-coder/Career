"""Versioned contracts shared by Python command adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

HELPER_ENVELOPE_SCHEMA = "career_python_helper_v1"


def helper_envelope(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Add the required subprocess contract version to a helper payload."""

    supplied_schema = payload.get("schema")
    if supplied_schema is not None and supplied_schema != HELPER_ENVELOPE_SCHEMA:
        raise ValueError("Helper payload uses an incompatible schema version.")
    return {"schema": HELPER_ENVELOPE_SCHEMA, **payload}


def helper_json(
    payload: Mapping[str, Any],
    *,
    indent: int | None = None,
    sort_keys: bool = False,
) -> str:
    """Serialize one dashboard/Raycast helper response consistently."""

    return json.dumps(
        helper_envelope(payload),
        ensure_ascii=False,
        indent=indent,
        sort_keys=sort_keys,
    )
