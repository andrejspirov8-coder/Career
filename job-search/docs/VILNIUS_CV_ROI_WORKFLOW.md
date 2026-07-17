# Vilnius CV ROI Workflow

Use this for the next 30 days to spend time where it is most likely to create interviews.

## Target Mix

- 35% operations and customer-operations leadership.
- 25% premium retail and retail leadership.
- 25% business/process operations.
- 10% implementation and customer success.
- 5% IT/business support.

## Weekly Routine

1. Keep daily job alerts active on CVBankas, CV-Online, Work in Lithuania, and LinkedIn, routed to Gmail label `Career/Job Alerts`.
2. Review `Fresh Live Matches` in the dashboard or run `Job: Daily Queue`.
3. Apply only to strong, geographically eligible roles. Prefer the top 5-10 unless a role is strategically valuable.
4. Spend up to 20 minutes tailoring a normal application. Spend more only for a top 3 role.
5. Log every application in `pipeline/applications.csv`.
6. Run `python3 tools/variant_performance.py`, `python3 tools/variant_performance.py --by source`, and `python3 tools/variant_performance.py --roi` at the end of the week.

## What To Log

- `match_score` and `match_confidence` from `MATCH.json`.
- `salary_range` from the advert, if shown.
- `tailored_cv`: `yes` or `no`.
- `response_date` when any employer or recruiter responds.
- Short note: keyword gaps added, ignored, or missing proof.

## Decision Rule

After 10 applications per lane, double down on the lane with the best interview rate. If two lanes are close, prefer the one with higher salary range and faster response time.

Do not add new CV claims unless the proof is already in `cv/CV_METRICS_INTAKE.md`.
