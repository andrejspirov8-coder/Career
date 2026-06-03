# Security policy

## Operating rule

This workspace is local-first. Keep credentials, browser sessions, recruiter exports, and outreach logs out of Git.

## Never commit

- `.env` or `.env.*` files
- LinkedIn/browser profiles or cookies
- recruiter CSV exports containing personal data
- generated PDFs or application packs
- screenshots from logged-in pages
- raw message/invitation logs

## Live LinkedIn dispatch

Live connection sending is intentionally gated. Use dry-runs and review queues by default.

Allowed default flow:

```bash
cd job-search
uv run python tools/recruiter_orchestrate.py daily --headed --dry-run
```

Live dispatch requires an explicit command-line acknowledgement:

```bash
uv run python tools/recruiter_orchestrate.py dispatch --headed --tier tier_1 --max 3 --allow-live-dispatch
```

Do not run high-volume connection automation. Stop immediately on CAPTCHA, checkpoint, account warning, unusual activity, or unclear page state.

## Local hardening checklist

- Use a dedicated browser automation profile.
- Do not reuse your daily browser profile for automation.
- Keep all generated state under `job-search/pipeline/`, `job-search/linkedin/run_logs/`, and `job-search/linkedin/.browser-profile/`.
- Review `.gitignore` before every commit.
- Prefer CSV review queues over direct send actions.
