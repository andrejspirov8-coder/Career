# Operations runbook

This runbook is the current operational source of truth. Older health reports and implementation notes are historical snapshots; trust fresh command output over those files.

Run commands from the private repository root, which is the folder containing
`pyproject.toml`. Treat adjacent or older Career folders as reference only.

## Principle

Separate sourcing, ranking, review, and dispatch. Automation may prepare decisions; live outbound actions require explicit approval.

## Pre-work checks

Before changing automation logic or running a live recruiter session:

```bash
git status --short
uv run ruff check tools cv tests
uv run pytest -q
make doctor
```

`make doctor` may report the browser debugger as offline when Chrome is not already running in automation mode. That is not a code failure by itself.

## Local web control center

Start both the web app and scheduler worker:

```bash
make dashboard-dev
```

Then sign in at `http://127.0.0.1:3000/login`. Use **Automation** to run the
safe daily search, inspect run history, retry a partial or failed run, and
choose a daily time. The schedule is active only while the supervisor or
worker is running and the Mac is awake. Check **Notifications** for one private
queue of completed searches, strong roles, deadlines, follow-ups, and source
problems.

When a login secret is missing, the supervisor creates one automatically in
the ignored `dashboard/.env.local` file with private permissions. Enter it on
the first browser login; the remembered cookie normally survives restarts.
Use **Settings → Secure local storage** to move the secret into macOS Keychain.
Do not print, paste into documentation, or commit the secret.

For a built production version:

```bash
make dashboard-start
```

`make dashboard-start` builds before it starts, so a separate build command is
not required.

In production, **Settings → App version** detects dashboard files that are newer
than the running build. When the supervisor is available, **Rebuild and restart
safely** stops only the web child, builds the current files, and starts it again.
The worker remains supervised. A failed build restores the prior `.next` build
and records the failure in Settings. The request is private, single-use, and
fixed; browser input cannot add a command, path, or executable.

`make dashboard-worker` runs the schedule without the web server. Manual web
actions can still start one-shot workers. The run database and private logs
live under `state/` and are ignored by git.

The scheduler has two fixed actions only: safe opportunity discovery and CV
PDF rebuild. Web input can never supply a command, path, or executable. The
**Automation** page also reports whether each configured source is healthy,
stale, limited, or failed.

If a schedule check happens more than 30 minutes after the planned time, the
worker labels the one daily run as a catch-up after wake. The normal daily key
still prevents a duplicate. Desktop notifications are optional and local to the
browser; they appear only while a signed-in dashboard tab is open.

## CV Studio workflow and recovery

Use **CV Studio** for routine CV changes:

1. Choose one of the six fixed variants.
2. Edit a section and keep every claim interview-defensible.
3. Click **Save & rebuild this CV**.
4. Review the visual and ATS previews.
5. Choose a saved opportunity to compare wording and gaps.

Saving validates the complete source, snapshots the previous source under
`state/cv_versions/`, and builds the selected outputs privately before replacing
the current files. If validation or PDF generation fails, the saved source and
current outputs remain unchanged. **Source history → Restore** requires a
confirmation, keeps the current source as another recovery point, and rebuilds
only the selected variant.

To rebuild one fixed variant without changing its source:

```bash
uv run python cv/build_cv_pdf.py --variant business-process-operations
```

Encrypted workspace backups include CV sources, outputs, and CV Studio recovery
versions. Do not edit or delete files under `state/cv_versions/` manually.

## Minimal daily workflow

For job leads, start with the manual opportunity queue:

```bash
cd job-search
make daily-queue
```

Review `Apply Today`, `Needs CV Tailoring`, `Missing Outcome`, and `Follow Up`
in the dashboard after checking `Daily Queue`. If the dashboard is not already
running, start it with `make dashboard-dev`. Apply manually on the employer
or job-board site, then use `Log Application` so weekly analytics can learn
from source, CV variant, score, and outcome. In Opportunities, `J` and `K` move
through the visible role list, and a completed decision selects the next role
without triggering any application or outbound action.

For LinkedIn recruiter scouting, keep live sending off unless you intentionally
use the approval-ledger flow:

```bash
cd job-search
uv sync --all-groups
uv run python -m career_job_search.recruiters.orchestrator preflight
uv run python -m career_job_search.recruiters.orchestrator scout --headed
uv run python -m career_job_search.recruiters.orchestrator plan --tier tier_1
uv run python -m career_job_search.recruiters.orchestrator dispatch --headed --tier tier_1 --dry-run --max 3
```

Review generated files:

- `pipeline/recruiter_action_plan.jsonl`
- `pipeline/recruiter_session_state.json`
- `pipeline/recruiters.csv`

Weekly review:

```bash
make weekly-review
```

The **Insights** page provides the same outcome learning in a friendlier form.
It labels conversion rates as early signals until at least 10 applications are
logged, so a single result does not drive a strategy change.

## Live dispatch gate

Only after reviewing the queue and approving the exact notes:

```bash
make approve-session
make check-approvals
LINKEDIN_SEND_MODE=cli_gated uv run python -m career_job_search.recruiters.orchestrator dispatch --headed --tier tier_1 --max 3 --allow-live-dispatch
```

Use the smallest batch first. Stop after any platform warning, CAPTCHA, unexpected modal, or repeated selector failure.

## Rollback

Live outbound actions cannot be fully rolled back. Before a risky local change,
create an encrypted workspace backup:

```bash
make dashboard-backup
```

To restore, stop the dashboard service and use the exact backup filename shown
under Settings. The command prompts for the passphrase and `RESTORE`, verifies
every path and hash, and creates a pre-restore safety backup:

```bash
make dashboard-restore BACKUP=career-backup-YYYYMMDDTHHMMSSZ-abcdef.career-backup
```

Restore overlays verified private files. It does not delete unrelated files.

## Failure modes

| Failure | Likely cause | Smallest fix |
| --- | --- | --- |
| `Missing config` | Wrong working directory | Run from `job-search/` |
| Browser asks for login | Fresh automation profile | Login manually in headed mode |
| CAPTCHA/checkpoint | Platform risk signal | Stop the run; wait; reduce volume |
| Empty dispatch queue | Plan filtered all rows | Inspect action plan and tier filter |
| Schedule did not run | Worker was closed or Mac was asleep | Start `make dashboard-dev` or `make dashboard-worker`, then use **Run today's search** |
| Notification is not on the desktop | Alerts are off, browser permission is blocked, or no dashboard tab is open | Open **Notifications**, enable alerts once, and keep a signed-in tab open |
| Worker shows offline | Continuous service is not running | Manual runs still work; restart the dashboard supervisor for scheduling |
| Dashboard login says token missing | The app was started outside the supervisor or the secret is absent | Restart with `make dashboard-dev`; it creates the private local secret when needed |
| Settings says `Update needed` | Dashboard files changed after the production build started | Use **Rebuild and restart safely**, or restart with `make dashboard-start` |
| Safe dashboard rebuild failed | The new dashboard source did not build | Read the short error in Settings; the supervisor restores and serves the last working build |
| CV Studio save failed | The source is incomplete or a selected PDF could not build | Read the page error, keep the editor open, correct the named section, and retry; current saved files remain unchanged |
| A CV edit needs undoing | The source was saved but should be reverted | Open **CV Studio → Source history**, review the date and hash, then confirm **Restore** |
| Keychain shows unavailable | The app is not running on macOS or Keychain access failed | Keep the ignored private settings-file option and retry from the logged-in Mac user |
| Restore is disabled in Settings | The automation worker is still online | Stop the service and use `make dashboard-restore BACKUP=<filename>` |
| Local drafting is offline | Ollama is not running at `127.0.0.1:11434` | Start Ollama or leave drafting off; no data is sent elsewhere |
| CI dependency error | Lock/dependency drift | Run `uv lock && uv sync --all-groups` locally |

## Optional local drafting

Local drafting is off by default. When explicitly enabled in Settings, it uses
only an installed Ollama model at `http://127.0.0.1:11434`. The dashboard does
not save prompts, although the separate Ollama service controls its own logs.
Drafts are returned to editable application fields and remain unsaved until
**Save application plan** is clicked. They never trigger an application,
LinkedIn message, email, or browser action. Review every claim before use.

## Opportunity intelligence workflow

Use this for broader job leads. It reads local inbox jobs and configured safe
sources, scores them against CV variants, and writes local state under
`state/`.

```bash
cd job-search
uv run python -m career_job_search.opportunities.orchestrator --config config/opportunities.example.yaml discover --dry-run
uv run python -m career_job_search.opportunities.orchestrator --config config/opportunities.example.yaml discover
uv run python -m career_job_search.opportunities.orchestrator match
uv run python -m career_job_search.opportunities.orchestrator --config config/opportunities.example.yaml daily-queue
uv run python -m career_job_search.opportunities.orchestrator report
```

Review `/opportunities` in the dashboard. Safe actions are limited to local
review, status updates, and local application-pack generation. Apply manually on
the employer or job-board site; this repo does not auto-submit applications.

The opportunity workflow can read public Greenhouse, Lever, Ashby, and
SmartRecruiters postings from `config/opportunities.example.yaml`. It can also
import official alert emails from the Gmail label `Career/Job Alerts`. Gmail
must be reconnected with search/read permission before that source works.
The dashboard scheduler explicitly passes `--exclude-linkedin`, so it never
starts direct LinkedIn browser discovery. The separate LinkedIn browser tools
remain available only for intentional, manual CLI use. If a complete manual
snapshot is imported, missing eligible rows become `unverified`; an incomplete
or failed snapshot changes nothing. The web app itself cannot start that source.
Rediscovered roles preserve first-seen and manual workflow state; incomplete or
failed sources never close existing jobs. The daily automation prints only
`data.new_live_jobs`, including the direct listing URL and recommended visual or
ATS CV PDF. LinkedIn job-alert URLs are accepted as `job_alert` records and
checked with the same live-evidence rules. A role is new to the output when it
is currently live and not already in the shown-jobs ledger; it does not have to
be first discovered today. It shows at most 10 rows and the delivery ledger at
`state/opportunities.sqlite3` records only those rows actually shown, so the
same vacancy cannot appear in a later fresh list. Preview runs do not become
permanent daily-run history.

Exit code `2` means the run produced usable results but one or more sources
failed. Review `source_results` and `data.source_issues` in the JSON instead of
treating it as a zero-job day. Capped ATS feeds and the company watchlist are
reported as coverage or monitor-only issues; they do not create fake job
listings. Exit code `1` means the run failed.

## Approval-ledger dispatch flow

Live LinkedIn dispatch is gated three times:

1. Send mode: set `LINKEDIN_SEND_MODE=cli_gated`.
2. CLI intent: pass `--allow-live-dispatch` and an explicit `--max 1..3`.
3. Persistent approval: approve the exact session note into SQLite before dispatch.

Default `LINKEDIN_SEND_MODE=manual` blocks browser-click dispatch. Use manual mode for normal work: open the profile, copy the approved note, and record sent/pending/replied outcomes locally.

Recommended sequence:

```bash
cd job-search
make scout
make plan
make dispatch-dry
make approve-session
make check-approvals
LINKEDIN_SEND_MODE=cli_gated uv run python -m career_job_search.recruiters.orchestrator dispatch --headed --tier tier_1 --max 3 --allow-live-dispatch
```

The approval check hashes the final note text. If a note is regenerated or edited after approval, the approval no longer matches and live dispatch is blocked until the updated note is approved again.

The local SQLite state lives at:

```text
job-search/state/recruiter_state.sqlite3
```

This path is ignored by git. Treat CSV/JSONL files as review/export artifacts; use the SQLite database as the local approval and send ledger.
