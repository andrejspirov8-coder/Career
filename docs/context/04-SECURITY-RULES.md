# Security policy

## Operating rule

This private workspace is local-first. Keep credentials, browser sessions, recruiter exports, opportunity data, and outreach logs out of Git.

## Never commit

- `.env` or `.env.*` files
- LinkedIn/browser profiles or cookies
- dashboard tokens or session cookies
- recruiter CSV exports containing personal data
- generated PDFs or application packs
- screenshots from logged-in pages
- raw message or invitation logs

## Local dashboard

The dashboard binds to `127.0.0.1` and requires `CAREER_DASHBOARD_TOKEN`. Generate a local token, do not commit it, and sign in at `/login`.

```bash
export CAREER_DASHBOARD_TOKEN="$(openssl rand -hex 24)"
make dashboard-dev
```

## Live LinkedIn dispatch

Live connection sending is intentionally gated. Use dry runs and review queues by default.

```bash
uv run python tools/recruiter_orchestrate.py daily --headed --dry-run
```

Browser-click dispatch requires CLI-gated mode, an explicit maximum from one to three, the acknowledgement flag, and current approval for every exact note.

```bash
LINKEDIN_SEND_MODE=cli_gated uv run python tools/recruiter_orchestrate.py dispatch --headed --tier tier_1 --max 3 --allow-live-dispatch
```

Stop immediately on CAPTCHA, checkpoint, account warning, unusual activity, or unclear page state.

## Local hardening checklist

- Use a dedicated browser automation profile.
- Do not reuse your daily browser profile for automation.
- Keep generated state under `pipeline/`, `state/`, `linkedin/run_logs/`, and `linkedin/.browser-profile/`.
- Review `.gitignore` before every commit.
- Prefer review queues over direct send actions.
- Run `make verify-release` before proposing a merge.
