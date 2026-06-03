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

## Setup

```bash
cd /Users/andrejspirov/Downloads/Career-main/raycast-job-search-hub
npm install
npm run dev
```

Raycast should open the extension in development mode. Search for commands starting with `Job:`.

The extension uses `CAREER_JOB_SEARCH_ROOT` when set. If it is not set, it looks for:

1. `~/Downloads/Career-main/job-search`
2. `~/Career/job-search`

## Checks

```bash
npm test
npm run typecheck
npm run build
```

## Notes

- Set `CAREER_JOB_SEARCH_ROOT` if your job-search workspace lives somewhere else.
- `applications.csv` is upgraded to include deadline and ROI columns the first time the extension writes to it.
- `Job: Deadlines` creates a temporary `.ics` calendar file and opens it with Calendar.
