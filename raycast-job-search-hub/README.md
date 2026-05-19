# Job Search Hub

Raycast extension for Andrej's local job-search toolkit in `/Users/andrejspirov/Career/job-search`.

## What It Adds

- `Job: New` creates a `.job.txt` file in `job-search/inbox/jobs`.
- `Job: Match All` runs `tools/batch_match_and_pack.py`.
- `Job: Review` lists generated packs from `job-search/packs`.
- `Job: Log Application` appends to `pipeline/applications.csv`.
- `Job: Analytics` shows funnel, variant, and job-source results.
- `Job: Deadlines` shows applications with deadlines in the next 7 days.
- `Job: Rebuild CVs` regenerates all CV PDFs and Canva paste files.

## Setup

```bash
cd /Users/andrejspirov/Career/raycast-job-search-hub
npm install
npm run dev
```

Raycast should open the extension in development mode. Search for commands starting with `Job:`.

## Checks

```bash
npm test
npm run typecheck
npm run build
```

## Notes

- Paths are intentionally hardcoded to `/Users/andrejspirov/Career/job-search`.
- `applications.csv` is upgraded to include `deadline_date` the first time the extension writes to it.
- `Job: Deadlines` creates a temporary `.ics` calendar file and opens it with Calendar.
