"""CLI entry point for career-job-search — allows `python -m career_job_search`."""

import sys

from career_job_search.opportunities.orchestrator import main as orchestrator_main

if __name__ == "__main__":
    raise SystemExit(orchestrator_main(sys.argv[1:]))
