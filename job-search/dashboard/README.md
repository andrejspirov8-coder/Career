# Career Workspace Dashboard

This local-only web app is the main control center for daily job-search work.
It shows automation history, ranked opportunities, CV variants, and the manual
recruiter-review queue without exposing private data on the network.

## First run

1. From the repository root, run `make dashboard-dev`.
2. Open `http://127.0.0.1:3000/login`.
3. On the first browser login only, read the automatically generated secret
   from `dashboard/.env.local` and enter it once. Do not copy that file outside
   this Mac or commit it.

For normal daily use, `make dashboard-start` now builds the production app
before starting it, so one command is enough after a fresh clone or code update.

The **App version** panel in Settings compares the running production build with
the current dashboard files. If it reports **Update needed**, the managed
service can rebuild and restart only the web app from that panel. The background
worker stays supervised, and a failed build restores the last working web build.
The browser action is fixed; it cannot supply a command, executable, or path.

The supervisor starts both the web app and the local background worker. The
server stores only an HMAC-derived session value in an `HttpOnly`,
`SameSite=Strict` cookie. The login page remembers this browser for 30 days by
default, including across server restarts. Uncheck that option to use an
eight-hour session instead. Development and production commands bind to
`127.0.0.1`, which means only this Mac can reach them.

After signing in, **Settings → Secure local storage** can move the login secret
into macOS Keychain. The service prefers Keychain on later starts; disabling
that option safely copies the secret back to the ignored local settings file.

## What the dashboard controls

- **Today:** a morning briefing with the next task, daily progress, shortlist, follow-ups, and CV status.
- **Notifications:** one private queue for completed searches, strong roles, application deadlines, follow-ups, and source problems.
- **Automation:** run a safe job search, rebuild CVs, inspect results, cancel or retry runs, and choose a daily time.
- **Opportunities:** rank and review roles, load full evidence on selection, move with `J`/`K`, advance after decisions, generate local packs, and record manual applications.
- **Applications:** keep selected CVs, pack files, deadlines, reminders, notes, and editable cover-letter or follow-up drafts together.
- **Insights:** show the application funnel, response time, source and CV performance, and recruiter outcomes without returning descriptions or notes.
- **CV Studio:** edit any fixed CV source by section, compare its saved wording with a saved job, rebuild one variant, preview both PDF formats, and restore an earlier source.
- **Recruiter Review:** rank saved recruiter records, prepare one exact note, open a validated LinkedIn profile, and record an outcome you completed manually.
- **Settings:** edit search preferences, move the secret to Keychain, create encrypted backups, opt into macOS sign-in startup, and optionally enable localhost-only drafting.

The scheduled job search explicitly excludes direct LinkedIn browser discovery.
The dashboard cannot search LinkedIn, send connection requests, send messages,
or submit job applications.

## Daily schedule

Enable the schedule under **Automation** and choose a Europe/Vilnius time. The
worker deduplicates the daily run, so restarting the service cannot create a
second scheduled run for the same calendar day. Multiple workers also claim
jobs atomically, so only one worker executes a queued run.

When the worker next checks the schedule more than 30 minutes after the planned
time, it records the one daily run as a **catch-up after wake**. The same daily
deduplication still applies, so waking or restarting cannot queue a second run.

The schedule runs only while `make dashboard-dev`, `make dashboard-start`, or
`make dashboard-worker` is running. The Mac must be awake and online. Automatic
startup is off by default. Clicking **Enable for next sign-in** under Settings
writes a local macOS LaunchAgent; setup and tests never install or load it.

Manual dashboard actions still work when the continuous worker is offline: each
action starts a private one-shot worker.

## Private notifications

The inbox derives updates from existing local automation, opportunity, and
application records. Read, snooze, dismiss, and desktop-delivery state lives in
`state/notifications.sqlite3`; it is ignored by Git and included in encrypted
workspace backups. Browser actions are a fixed allowlist and cannot supply a
command or an outside URL.

Desktop alerts are off until **Enable desktop alerts** is clicked and browser
permission is granted. Existing items are marked as already delivered when the
setting is enabled, so the Mac is not flooded with old alerts. New alerts can
appear only while a signed-in dashboard tab is open. No email, phone, or outside
notification service is used.

## CV Studio

Open **CV Studio**, choose a variant, and edit one section at a time. The page
keeps the underlying Markdown structure intact and shows whether changes are
still unsaved. **Save & rebuild this CV** validates the source, creates a private
recovery version, and builds the selected visual PDF, ATS PDF, and Canva text in
a temporary location before replacing any current file. A failed build leaves
the saved source and current outputs unchanged.

The job comparison reads the saved source and existing local opportunity data;
it does not invent experience or change the CV. Only add a suggested phrase
when it is true and interview-defensible. **Source history** can restore an
earlier version after explicit confirmation. Encrypted workspace backups include
these private source versions.

## Backup and recovery

The readable `/api/export` download is useful for inspection but is not an
encrypted recovery copy. Use **Settings → Encrypted workspace backup** for CVs,
application packs, local databases, preferences, application notes, and
pipeline data. Encryption uses a passphrase held only for the request. Keep it
in a password manager because the app cannot recover it.

Restore is blocked while the automation worker is online. Stop the service and
run the command shown in Settings:

```bash
make dashboard-restore BACKUP=career-backup-YYYYMMDDTHHMMSSZ-abcdef.career-backup
```

The restore validates paths and hashes, overlays verified private files, and
creates a pre-restore encrypted safety backup. It does not delete unrelated
workspace files.

## Optional local drafting

Local drafting is disabled until you enable it in Settings and choose an Ollama
model that is already installed. The dashboard connects only to
`http://127.0.0.1:11434`, does not store prompts itself, and returns text to an
editable field. Ollama is a separate local service and controls its own logs.
Every draft requires a click, remains unsaved until **Save application plan**,
and is never submitted or sent automatically.

## End-to-end tests

These tests build and start the production dashboard, then use local fixtures
and mocked dashboard action calls. They never dispatch LinkedIn actions or
submit applications.

```bash
cd dashboard
npm run e2e:install
CAREER_DASHBOARD_TOKEN=e2e-token npm run e2e
```

Complete local checks:

```bash
npm test
npm run typecheck
npm run build
npm audit --audit-level=high
```

## API

- `POST /api/auth/login` creates the local session cookie; `POST /api/auth/logout` clears it.
- `GET /api/overview` returns the current repository snapshot after authentication.
- `GET /api/automation/overview`, `GET /api/automation/runs/{id}`, and `POST /api/automation/actions` control the fixed local job-search and CV-build actions.
- `GET /api/notifications/overview` and `POST /api/notifications/actions` provide the private inbox and its fixed read, snooze, dismiss, and desktop-delivery actions.
- `GET /api/cvs/overview`, `GET /api/cvs/{variant}/{format}`, and `POST /api/cvs/actions` provide the protected CV files and full rebuild action.
- `GET` and `POST /api/cvs/studio/{variant}` load, save, rebuild, or restore one fixed CV variant; `GET /api/cvs/studio/{variant}/compare?opportunity={id}` returns a local job comparison.
- `GET /api/recruiter/overview` and `POST /api/recruiter/actions` provide the human-controlled recruiter workspace.
- `GET /api/opportunities/overview`, `GET /api/opportunities/{id}`, and `POST /api/opportunities/actions` provide summarized queues and on-demand detail.
- `POST /api/opportunities/capture` stores a pasted link or job text without browser-side fetching.
- `GET /api/applications/overview`, `POST /api/applications/actions`, and `GET /api/applications/calendar` provide the application workspace.
- `GET /api/insights/overview` returns aggregate-only outcome analytics.
- `GET /api/preferences` and `POST /api/preferences` provide editable search preferences.
- `GET /api/settings/overview`, `POST /api/settings/actions`, and protected backup downloads provide local service and recovery controls.
- `GET /api/ai/status`, `POST /api/ai/settings`, and `POST /api/ai/draft` provide opt-in localhost-only drafting.
- `GET /api/search` provides bounded global search across jobs, recruiters, and CV variants.
- `GET /api/export` downloads a protected local JSON backup of opportunities and applications.

All private API responses use `no-store` headers. Browser changes require a
same-origin request. Script clients may continue to use
`x-career-dashboard-token` or a Bearer token.
