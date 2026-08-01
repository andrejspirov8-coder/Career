# Career job-search workspace

This folder keeps CV source files, finished PDFs, job adverts, matching results, and application tracking in one place.

## Start here

This README is the current source of truth for daily use.

- This private repository checkout is the active workspace.
- Treat any adjacent or older Career folders as reference-only copies; do not let automation write there.
- Use the local dashboard as the main daily control center.
- Use Raycast as a quick keyboard-driven alternative for individual tasks.
- Run the checks in `Development checks` before adding more automation.
- Keep live LinkedIn dispatch off unless you intentionally approve a reviewed queue.

Raycast is the macOS command launcher opened with a keyboard shortcut.

## Current repo ownership

The active Git repository is the folder containing this README. Python tools,
the dashboard, security policy, and GitHub checks all live here. Adjacent
legacy copies remain untouched until clean-clone verification and a separate
deletion request.

Current release risk: this workspace has a large dirty worktree. Before adding or expanding scheduled automation, run `git status --short` and verify that unrelated local changes are intentional.

## Daily flow

1. Start the local service with `make dashboard-dev`.
2. Sign in at `http://127.0.0.1:3000/login`.
3. Check **Notifications** for missed searches, strong roles, deadlines, and follow-ups.
4. Open **Automation** and run today's safe job search, or enable its daily schedule.
5. Work through the ranked **Daily Queue** under **Opportunities**. Use `J` and `K` to move between visible roles; after a decision closes a role, the next one is selected automatically.
6. Use **Applications** to keep the selected CV, pack, deadline, reminder, cover letter, and follow-up together.
7. Apply yourself, then record the outcome so **Insights** can learn from it.
8. Use **Recruiters** to prepare a LinkedIn note, send it yourself in your normal browser, and record the result.

The service creates a private login secret automatically when one is missing.
Enter it only on the first browser login; the remembered `HttpOnly` cookie
normally survives server restarts. Under **Settings**, you may move the secret
from the ignored `dashboard/.env.local` file into macOS Keychain. The secret is
never displayed by the web app and must never be committed.

For broader job discovery, run `Job: Daily Queue` in Raycast or:

```bash
make daily-queue
```

This queues the same safe search in a private background worker. Open the local
dashboard separately with `make dashboard-dev`. Start with `Daily Queue`, then
use `Apply Today`, `Needs CV Tailoring`, `Missing Outcome`, and `Follow Up` to
keep every lead in a clear state. Use `Log Application` only after you have
manually submitted the application.

## CV source of truth

Use **CV Studio** in the local dashboard for normal editing. Choose one of the
six variants, edit one section, compare the saved wording with a saved job, and
review the visual and ATS previews side by side. **Save & rebuild this CV**
builds only the selected variant and creates a private recovery snapshot before
changing its source.

The Markdown files in `cv/` remain the source of truth. These are the editable
CV sources:

| Variant | Source file | Use for |
| --- | --- | --- |
| `luxury-retail` | `cv/andrej-spirov-cv-luxury-retail.md` | Premium retail, boutique, store leadership |
| `luxury-retail-lt` | `cv/andrej-spirov-cv-luxury-retail-lt.md` | Lithuanian-language retail roles |
| `operations-management` | `cv/andrej-spirov-cv-operations-management.md` | Operations, service, multi-site leadership |
| `operations-management-lt` | `cv/andrej-spirov-cv-operations-management-lt.md` | Lithuanian-language operations, process management, improvement, and customer experience leadership |
| `business-process-operations` | `cv/andrej-spirov-cv-business-process-operations.md` | Business/process analyst, customer operations, and implementation support |
| `it-business` | `cv/andrej-spirov-cv-it-business.md` | Business systems, application/automation support, and technical or vendor operations |

Before adding a metric to a CV, record it in `cv/CV_METRICS_INTAKE.md` so it is easy to defend in an interview.

CV Studio job comparison uses the last saved source. If the editor shows
**Unsaved edits**, save and rebuild before treating the comparison as current.
Earlier sources appear under **Source history** and can be restored with an
explicit confirmation. Their private files live under `state/cv_versions/` and
are included in encrypted workspace backups.

## Finished files

Send or upload files from `output/`.

| File type | Location | When to use |
| --- | --- | --- |
| Visual PDF | `output/andrej-spirov-cv-<variant>.pdf` | Emailing a person or sharing a polished CV |
| ATS PDF | `output/andrej-spirov-cv-<variant>-ats.pdf` | Online application portals |
| Canva paste text | `output/canva/` | Rebuilding the design in Canva |

ATS means applicant tracking system: the software many hiring portals use to read uploaded CVs.

Rebuild all CV outputs:

```bash
uv run python cv/build_cv_pdf.py --all
```

Rebuild one variant without changing its source:

```bash
uv run python cv/build_cv_pdf.py --variant business-process-operations
```

Or use Raycast: `Job: Rebuild CVs`.

## Job matching

Job adverts live in `inbox/jobs/` as `.job.txt` files. Each file uses this shape:

```text
TITLE: Job Title
COMPANY: Company Name
URL: https://example.com/jobs/123
SOURCE: linkedin
JOB_ID:
---
Paste the full job advert here.
```

Application packs are generated in `packs/<job-id>/`. Each pack contains the match result, keyword gaps, and absolute paths to the recommended PDFs.

## Application tracking

Log every submitted application in `pipeline/applications.csv`.

For the next 30 days, use this mix unless the data says otherwise:

- 60% business analyst / process analyst / operations analyst
- 25% customer operations / customer success / implementation support
- 15% premium retail / store leadership fallback

Use consistent source names:

| Channel | Source value |
| --- | --- |
| LinkedIn | `linkedin` |
| CVbank.lt | `cvbank` |
| CV.lt | `cv_lt` |
| Startup or tech listing | `startup_lt` |
| Work in Lithuania | `work_in_lt` |
| Employer site | `company_site` |
| Recruiter | `recruiter` |
| Indeed | `indeed` |

Open **Insights** after logging applications. Rates remain labelled as early
signals until at least 10 applications exist. The terminal reports remain
available when needed:

```bash
python3 -m career_job_search.cvs.performance
python3 -m career_job_search.cvs.performance --by source
```

## Local dashboard privacy and recovery

- The web server binds to `127.0.0.1`; it is not available to other devices.
- **Settings → Secure local storage** can move the login secret to macOS Keychain.
- **Settings → Encrypted workspace backup** creates an authenticated encrypted backup. The passphrase is never stored.
- Restore verifies every file, rejects unsafe archive paths, requires the exact word `RESTORE`, and creates a safety backup first.
- **Settings → Open after macOS sign-in** writes a LaunchAgent only after you click the enable button. It is not installed automatically by setup or tests.
- **Local drafting** is off by default. When enabled, it calls only Ollama at `127.0.0.1`, produces editable drafts, and never applies or sends anything.
- **Settings → App version** reports when the running production screen is older than the dashboard files. When the managed service is running, its fixed rebuild action keeps the worker online and restores the prior web build if rebuilding fails.
- **Notifications** are stored in the ignored local workspace and included in encrypted backups. Desktop alerts are optional, require one browser permission click, and work only while the dashboard is open.

Create a backup interactively from the terminal:

```bash
make dashboard-backup
```

To restore after stopping the dashboard service, use a filename shown under
**Settings**. The command prompts for the passphrase instead of putting it in
shell history:

```bash
make dashboard-restore BACKUP=career-backup-YYYYMMDDTHHMMSSZ-abcdef.career-backup
```

## Useful commands

```bash
# Install the complete locked workspace
make bootstrap

# Create a job file from the terminal
uv run python -m career_job_search.opportunities.new_job

# Match all inbox jobs
uv run python -m career_job_search.opportunities.batch

# Review generated packs
uv run python -m career_job_search.opportunities.review_packs --sort score

# Rebuild all CV PDFs and Canva text files
uv run python cv/build_cv_pdf.py --all
```

## LinkedIn recruiter scout (optional)

Playwright-backed recruiter scouting reuses CV keyword scoring (`matching_lib`). It launches an isolated automation browser profile (see `linkedin/config.yaml`). Documentation and safeguards live in [`linkedin/README.md`](linkedin/README.md).

Default mode is review-first:

```bash
uv run python -m career_job_search.recruiters.orchestrator daily --headed --dry-run
```

Live connection dispatch is off by default. Normal use is manual: review the
queue, open each profile, copy the approved note, and record the outcome.

CLI-click dispatch is available only if you explicitly switch the local mode to
`cli_gated` and pass the acknowledgement flag:

```bash
LINKEDIN_SEND_MODE=cli_gated uv run python -m career_job_search.recruiters.orchestrator dispatch --headed --tier tier_1 --max 3 --allow-live-dispatch
```

Use small batches only. Stop immediately on CAPTCHA, checkpoint, platform warning, unexpected modal, or repeated selector failure.

See [`docs/OPERATIONS_RUNBOOK.md`](docs/OPERATIONS_RUNBOOK.md) and [`SECURITY.md`](SECURITY.md).

## Broader opportunity pipeline

The local opportunity workflow produces a Vilnius-focused shortlist. It accepts
Vilnius onsite/hybrid roles and remote roles explicitly available from
Lithuania or the EU. Sources include official job-alert emails and read-only
public ATS feeds for Greenhouse, Lever, Ashby, and SmartRecruiters. It stays
human-in-the-loop: it can match roles, explain fit, generate application packs,
and track status, but it cannot auto-apply or scrape restricted job boards.

```bash
# Preview discovered opportunities without writing state
uv run python -m career_job_search.opportunities.orchestrator --config config/opportunities.example.yaml discover --dry-run

# Persist discovered rows, score them against CV variants, and report dashboard data
uv run python -m career_job_search.opportunities.orchestrator --config config/opportunities.example.yaml discover
uv run python -m career_job_search.opportunities.orchestrator match
uv run python -m career_job_search.opportunities.orchestrator --config config/opportunities.example.yaml daily-queue
uv run python -m career_job_search.opportunities.orchestrator report
```

Open the local dashboard at `/opportunities` to review saved views, inspect
evidence, generate packs for apply-ready roles, and log manual application
outcomes back to `pipeline/applications.csv`. Protected opportunity API calls use the same
`x-career-dashboard-token` header as the recruiter dashboard.

The dashboard schedule is off by default. When enabled under **Automation**, it
runs once per local calendar day at the selected Europe/Vilnius time while the
Career dashboard service is running and the Mac is awake. The scheduled command
uses official alert emails, configured company sources, and read-only public ATS
feeds. It explicitly disables direct LinkedIn browser discovery. LinkedIn job
URLs received in official alert emails can still enter the normal review queue.
If the service resumes more than 30 minutes after the planned time, it labels the
single daily run as a catch-up after wake. The same daily key prevents a second
scheduled run that day.

Direct LinkedIn browser tools remain available only for an intentional manual
CLI session. They are not started by the dashboard worker, and the web app has
no LinkedIn search or send action.

Create daily alerts on CVBankas, CV-Online, Work in Lithuania, and LinkedIn,
then route those messages to the `Career/Job Alerts` Gmail label.
The Gmail connector needs permission to search and read messages.
Imported email content is reduced to job fields and a short matching snippet;
full email bodies are not stored.

The normal run prints only `data.new_live_jobs`. A job is eligible when it is
currently live, geographically eligible, matched to a CV variant, and absent
from the shown-jobs ledger; it does not have to have been first discovered on
the same day. Each row includes the direct
listing URL, current liveness evidence, fit score, recommended CV variant, and
the visual and ATS PDF paths. The output is capped at 10 rows, and only rows
actually returned there are recorded in
`state/opportunities.sqlite3`'s `deliveries` table. A later run therefore
cannot show the same vacancy again. Source failures remain visible in
`source_results` and do not turn into a misleading zero-job result.

Raycast commands for daily opportunity work:

- `Job: Daily Queue`
- `Job: Discover Opportunities`
- `Job: Match Opportunities`
- `Job: Review Opportunities`

Weekly review:

```bash
make weekly-review
```

Older planning, implementation, and execution snapshots are preserved under
`archive/`. They are historical evidence, not current setup or operating
instructions.

## Development checks

Run these exact checks before expanding automation or calling the workspace stable:

```bash
# Python checks from job-search/
uv run ruff check tools cv tests
uv run pytest -q

# Dashboard build
cd dashboard
npm run typecheck
npm run build
```

Use `make verify-release` from the repository root for the complete release check, or `make smoke` for a faster workflow check.

The repository ownership and dependency rules are documented in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).


## Live dispatch approval ledger

Live connection dispatch now requires `LINKEDIN_SEND_MODE=cli_gated`, an explicit `--max 1..3`, `--allow-live-dispatch`, and a matching SQLite approval entry for the exact profile URL + note hash. The default `manual` mode blocks browser-click dispatch even when approvals exist.

```bash
make plan
make dispatch-dry
make approve-session
make check-approvals
LINKEDIN_SEND_MODE=cli_gated uv run python -m career_job_search.recruiters.orchestrator dispatch --headed --tier tier_1 --max 3 --allow-live-dispatch
```

Generated approval state is stored under `state/` and is intentionally gitignored.


## Dashboard

* Create `dashboard/.env.local` from the provided example, set a private token, then run `make dashboard-dev` and sign in at `http://127.0.0.1:3000/login`.
* Run `make dashboard-build` to validate the dashboard build.
* Run `make smoke` to exercise the full safe workflow set, including the dashboard.
