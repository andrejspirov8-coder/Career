"""Shared entrypoint for dashboard helper CLIs (--schema or main dispatch)."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any


def run(schema: Any, main: Callable[..., int]) -> int:
    if "--schema" in sys.argv:
        print(json.dumps(schema, indent=2))
        return 0
    return main()


def entry(schema: Any, main: Callable[..., int]) -> None:
    raise SystemExit(run(schema, main))
