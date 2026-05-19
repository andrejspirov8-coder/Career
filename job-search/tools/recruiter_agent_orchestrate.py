#!/usr/bin/env python3
"""Deprecated: use ``tools/recruiter_orchestrate.py`` (preflight/scout/plan/dispatch/daily/followup/report)."""

from __future__ import annotations

import sys


def main() -> None:
    print(
        "recruiter_agent_orchestrate.py is deprecated.\n"
        "Use: python3 tools/recruiter_orchestrate.py preflight\n"
        "     python3 tools/recruiter_orchestrate.py daily --headed --dry-run\n",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
