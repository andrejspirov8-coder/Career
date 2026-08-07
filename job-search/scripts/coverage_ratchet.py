#!/usr/bin/env python3
"""Enforce the coverage ratchet: fail if total coverage drops below baseline.

Run from the repository root (job-search/). Pass ``--update`` to record the
current total as the new baseline after a deliberate coverage improvement.

The ratchet replaces the previous static ``fail_under = 80`` floor, which was
never reachable (measured total ~60%) and therefore never enforced.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = REPO_ROOT / ".coverage-baseline"
JSON_REPORT = "/tmp/career_coverage_ratchet.json"
TOLERANCE = 0.5


def run_pytest_with_coverage() -> float:
    """Run the full suite with coverage and return the total percentage."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov",
            f"--cov-report=json:{JSON_REPORT}",
            "-q",
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    data = json.loads(Path(JSON_REPORT).read_text())
    return float(data["totals"]["percent_covered"])


def main() -> int:
    total = run_pytest_with_coverage()
    baseline = float(BASELINE_FILE.read_text().strip())

    if "--update" in sys.argv:
        BASELINE_FILE.write_text(f"{total:.1f}\n")
        print(f"[ratchet] baseline updated to {total:.1f}")
        return 0

    floor = baseline - TOLERANCE
    if total < floor:
        print(
            f"[ratchet] FAIL: coverage {total:.2f}% dropped below baseline "
            f"{baseline:.1f}% (floor {floor:.1f}%). "
            "Run 'make coverage-baseline-update' only after a deliberate "
            "coverage improvement."
        )
        return 1
    print(f"[ratchet] OK: coverage {total:.2f}% >= baseline {baseline:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
