# Job Search Hub

Raycast extension for Andrej's local job-search toolkit.

## What It Adds

- `Job: New` creates a `.job.txt` file in `job-search/inbox/jobs`.
- `Job: Match All` runs `tools/batch_match_and_pack.py`.
- `Job: Review` lists generated packs from `job-search/packs`.
- `Job: Log Application` appends to `pipeline/applications.csv`.
- `Job: Log Application` also captures match score, match confidence, salary range, tailored CV, and response date for weekly ROI review.
- `Job: Analytics` shows funnel, variant, and job-source results.
- `Job: Deadlines` shows applications with deadlines in the next 7 days.
- `Job: Rebuild CVs` regenerates all CV PDFs and Canva paste files.
- `Job: Daily Queue` refreshes broader opportunities, scores them, and summarizes the manual review queue.
- `Job: Discover Opportunities` finds broader Europe / remote-Europe leads.
- `Job: Match Opportunities` scores saved leads against CV variants and fit rules.
- `Job: Review Opportunities` opens `Top 5 Today` first and can prefill `Job: Log Application` from a selected opportunity.

## Setup

```bash
cd raycast-job-search-hub
npm ci
npm run dev
```

Raycast should open the extension in development mode. Search for commands starting with `Job:`.

Set **Job Search Folder** in the Raycast extension preferences. If it is blank, the extension uses `CAREER_JOB_SEARCH_ROOT`; if neither is set, it derives `~/Career/job-search` from your home directory.
Choose the private repository checkout containing `pyproject.toml`; older copies are reference only.

## Checks

```bash
npm test
npm run typecheck
npm run build
```

## Notes

- Set **Job Search Folder** in Raycast if your private job-search workspace lives somewhere else. `CAREER_JOB_SEARCH_ROOT` remains a compatible fallback for scripts.
- `applications.csv` is upgraded to include deadline, ROI, opportunity ID, pack folder, and application URL columns the first time the extension writes to it.
- `Job: Deadlines` creates a temporary `.ics` calendar file and opens it with Calendar.
