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

The dashboard binds to `127.0.0.1` and requires a private local login secret.
The supervisor creates one automatically when needed; do not pass it on a
command line, print it in logs, or commit it. Sign in at `/login`.

```bash
make dashboard-dev
```

The browser receives only an HMAC-derived `HttpOnly`, `SameSite=Strict` cookie,
not the original secret. Settings can move the secret into macOS Keychain. The
service reads it into the dashboard process environment without placing it in
the process argument list.

All pages and data routes require authentication. Cookie-authenticated changes
require same-origin protection. Script clients may use the token header or
Bearer authentication. The custom logout header is non-simple, so a cross-site
browser request cannot add it without a CORS preflight; the server grants no
cross-origin access.

The production update control accepts only one fixed rebuild request. Its
private request and status files are single-purpose, permission-restricted, and
excluded from backups. The supervisor ignores stale requests, keeps the
background worker supervised, and restores the previous web build when a new
build fails. No browser field can supply a shell command, executable, or path.

CV Studio accepts only the six configured variant names and bounded source
text; browser input cannot supply a filesystem path. It validates the complete
source and builds the visual PDF, ATS PDF, and Canva text in a private temporary
directory before atomically replacing current files. Save and restore operations
use a local lock and rollback copies to prevent partial updates. Recovery
versions are permission-restricted under `state/cv_versions/` and are available
only through authenticated routes.

The notification inbox is derived only from authenticated local workspace data.
Its read and delivery state is stored in ignored `state/notifications.sqlite3`.
Notification links must be internal dashboard paths, and browser changes use a
fixed action allowlist. Desktop delivery is an explicit browser permission; it
works only while the dashboard is open and does not contact an email, phone,
push, or other outside notification service.

## Encrypted recovery

Use the encrypted backup control or `make dashboard-backup` for local databases,
application notes, packs, CV sources, and outputs. Backups use authenticated
encryption and a passphrase that is never stored. Restore rejects absolute,
traversal, duplicate, unexpected, symlink, oversized, or hash-mismatched files.
It requires an offline worker, exact `RESTORE` confirmation, and creates a
pre-restore backup before writing verified files.

The readable `/api/export` file is not encrypted and should be handled as
private data.

## Local AI boundary

Web drafting is disabled by default and can connect only to Ollama at
`127.0.0.1:11434`; proxy settings and user-supplied URLs are not used. The
dashboard does not persist prompts and never sends or submits generated text.
Ollama is a separate local service and controls its own logs. Generated claims
must be reviewed before saving or using a draft.

## Live LinkedIn dispatch

Live connection sending is intentionally gated. Use dry runs and review queues by default.

```bash
uv run python -m career_job_search.recruiters.orchestrator daily --headed --dry-run
```

Browser-click dispatch requires CLI-gated mode, an explicit maximum from one to three, the acknowledgement flag, and current approval for every exact note.

```bash
LINKEDIN_SEND_MODE=cli_gated uv run python -m career_job_search.recruiters.orchestrator dispatch --headed --tier tier_1 --max 3 --allow-live-dispatch
```

Stop immediately on CAPTCHA, checkpoint, account warning, unusual activity, or unclear page state.

## Local hardening checklist

- Use a dedicated browser automation profile.
- Do not reuse your daily browser profile for automation.
- Keep generated state under `pipeline/`, `state/`, `linkedin/run_logs/`, and `linkedin/.browser-profile/`.
- Review `.gitignore` before every commit.
- Prefer review queues over direct send actions.
- Keep local drafting off when it is not needed.
- Keep encrypted backup passphrases in a password manager, separate from backup files.
- Run `make verify-release` before proposing a merge.
