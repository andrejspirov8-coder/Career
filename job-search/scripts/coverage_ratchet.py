#!/usr/bin/env python3
"""Enforce the coverage ratchet: fail if total coverage drops below baseline.

Run from the repository root (job-search/). Pass ``--update`` to record the
current total as the new baseline after a deliberate coverage improvement.

The ratchet replaces the previous static ``fail_under = 80`` floor, which was
never reachable (measured total ~60%) and therefore never enforced.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = REPO_ROOT / ".coverage-baseline"
TOLERANCE = 0.5


def run_pytest_with_coverage() -> float:
    """Run the full suite with coverage and return the total percentage."""
    fd, report_path = tempfile.mkstemp(
        prefix="career_coverage_ratchet_", suffix=".json"
    )
    os.close(fd)
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--cov",
                f"--cov-report=json:{report_path}",
                "-q",
            ],
            cwd=REPO_ROOT,
            check=True,
        )
        data = json.loads(Path(report_path).read_text())
        return float(data["totals"]["percent_covered"])
    finally:
        Path(report_path).unlink(missing_ok=True)


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
