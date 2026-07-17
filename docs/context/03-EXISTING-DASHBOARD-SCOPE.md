# Career Workspace Dashboard

Local Next.js dashboard MVP for the job-search workspace.

## Run

```bash
cd dashboard
npm ci
export CAREER_DASHBOARD_TOKEN="$(openssl rand -hex 24)"
npm run dev
```

Open `http://127.0.0.1:3000/login` and enter the token. The server stores only an HMAC-derived value in an eight-hour `HttpOnly`, `SameSite=Strict` cookie. Development and production commands bind to `127.0.0.1` only.

## End-to-End Tests

These tests use fake recruiter data and mocked dashboard action calls. They never dispatch LinkedIn actions.

```bash
cd dashboard
npm run e2e:install
CAREER_DASHBOARD_TOKEN=e2e-token npm run e2e
```

## API

* `POST /api/auth/login` creates the local session cookie; `POST /api/auth/logout` clears it.
* `GET /api/overview` returns the current repo snapshot as JSON after authentication.
* `GET /api/recruiter/overview` and `POST /api/recruiter/actions` accept the session cookie, `x-career-dashboard-token`, or a Bearer token.
* `GET /api/opportunities/overview`, `GET /api/opportunities/{id}`, and `POST /api/opportunities/actions` use the same token gate. The overview contains summaries only; full descriptions and evidence load on row selection.
* Browser state-changing requests must be same-origin. Header-token script clients remain compatible.
* Recruiter actions are manual-safe only: approve one note, copy a note, mark manual outcomes, skip, or move back to review. There is no dashboard live-send button.
* Opportunity actions are manual-safe only: review, skip, mark apply-ready, generate a local pack, mark applied, or snooze follow-up. There is no auto-apply button.

## Scope

* Local overview and recruiter operator console
* CV variants
* application and action-plan counts
* smoke and verification references
* Manual LinkedIn workflow: open profile, copy approved note, and record outcome locally
* Manual opportunity workflow: inspect match evidence, generate a pack, apply yourself, and record the outcome locally
* Opportunity saved views: Apply Today, Needs CV Tailoring, Missing Outcome, and Follow Up
