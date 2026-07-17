#!/usr/bin/env python3
"""Print the versioned CV catalogue for dashboard and Raycast adapters."""

from __future__ import annotations

from career_job_search.core.contracts import helper_json
from career_job_search.cvs.catalogue import load_cv_catalogue


def main() -> int:
    catalogue = load_cv_catalogue().model_dump(mode="json", by_alias=True)
    print(helper_json({"ok": True, "data": catalogue}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
