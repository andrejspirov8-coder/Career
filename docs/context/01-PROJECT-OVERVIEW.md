# Career

Local-first career operations workspace for CV variants, job matching, recruiter review queues, and Raycast-powered daily workflows.

## Default operating model

1. Keep Markdown CVs as the source of truth.
2. Generate PDFs and application packs from versioned source files.
3. Use automation to scout, score, rank, and draft.
4. Keep outbound recruiter actions review-first by default.
5. Require explicit approval for live LinkedIn dispatch.

## Main areas

| Path | Purpose |
| --- | --- |
| `job-search/` | Python CV, matching, recruiter, and pipeline tooling |
| `raycast-job-search-hub/` | Raycast extension for daily job-search commands |
| `.github/workflows/ci.yml` | CI for Python tests/lint and Raycast tests |
| `SECURITY.md` | Local secret, browser-profile, and dispatch safety rules |

## Bootstrap

```bash
cd job-search
./scripts/bootstrap.sh
```

Or manually:

```bash
cd job-search
uv sync --all-groups
uv run playwright install chromium
uv run pytest
```

## Safe recruiter workflow

```bash
cd job-search
uv run python tools/recruiter_orchestrate.py preflight
uv run python tools/recruiter_orchestrate.py scout --headed
uv run python tools/recruiter_orchestrate.py plan --tier tier_1
uv run python tools/recruiter_orchestrate.py dispatch --headed --tier tier_1 --dry-run --max 5
```

Live dispatch is gated and requires `--allow-live-dispatch`.

## Documentation

- Main workflow: [`job-search/README.md`](job-search/README.md)
- Security policy: [`SECURITY.md`](SECURITY.md)
- Operations runbook: [`job-search/docs/OPERATIONS_RUNBOOK.md`](job-search/docs/OPERATIONS_RUNBOOK.md)


## Current hardening layer

The job-search automation is review-first. Live LinkedIn dispatch requires:

1. `--allow-live-dispatch` on the CLI.
2. A matching approval ledger entry in `job-search/state/recruiter_state.sqlite3`.
3. An unchanged note hash between review and dispatch.

Use `cd job-search && make doctor` before running a dispatch session.
