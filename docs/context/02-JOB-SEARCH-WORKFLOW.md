# Career job-search workspace

This folder keeps CV source files, finished PDFs, job adverts, matching results, and application tracking in one place.

## Start here

This README is the current source of truth for daily use.

- Active workspace: `/Users/andrejspirov/Career/Career-main/job-search`.
- Treat `/Users/andrejspirov/Career/job-search` as reference only; do not let automation write there.
- Use Raycast for normal job-search work.
- Use the dashboard as read-only status only.
- Run the checks in `Development checks` before adding more automation.
- Keep live LinkedIn dispatch off unless you intentionally approve a reviewed queue.

Raycast is the macOS command launcher opened with a keyboard shortcut.

## Current repo ownership

The active Git repo is this folder: `/Users/andrejspirov/Career/Career-main/job-search`.

The Python tools, dashboard, Raycast extension, security policy, and GitHub checks now live in this private repository. The Raycast extension is under `raycast-job-search-hub/`. The adjacent legacy copy remains untouched until clean-clone verification and a separate deletion request.

Current release risk: this workspace has a large dirty worktree. Before adding or expanding scheduled automation, run `git status --short` and verify that unrelated local changes are intentional.

## Daily flow

1. Open Raycast and run `Job: New`.
2. Paste the full job advert into the new `.job.txt` file.
3. Run `Job: Match All` to score the advert against the CV variants.
4. Run `Job: Review` to inspect the recommended CV and keyword gaps.
5. Submit the right PDF yourself.
6. Run `Job: Log Application` after applying.
7. Run `Job: Analytics` to review which CV variants and sources perform best.

For broader job discovery, run `Job: Daily Queue` in Raycast or:

```bash
make daily-queue
```

This refreshes opportunities, scores them, and opens the local dashboard for manual review. Start with `Top 5 Today`, then use `Apply Today`, `Needs CV Tailoring`, `Missing Outcome`, and `Follow Up` to keep every lead in a clear state. Use `Log Application` only after you have manually submitted the application.

## CV source of truth

Edit Markdown files in `cv/`. These are the editable CV sources:

| Variant | Source file | Use for |
| --- | --- | --- |
| `luxury-retail` | `cv/andrej-spirov-cv-luxury-retail.md` | Premium retail, boutique, store leadership |
| `luxury-retail-lt` | `cv/andrej-spirov-cv-luxury-retail-lt.md` | Lithuanian-language retail roles |
| `operations-management` | `cv/andrej-spirov-cv-operations-management.md` | Operations, service, multi-site leadership |
| `operations-management-lt` | `cv/andrej-spirov-cv-operations-management-lt.md` | Lithuanian-language operations and customer experience leadership |
| `business-process-operations` | `cv/andrej-spirov-cv-business-process-operations.md` | Business/process analyst, customer operations, and implementation support |
| `it-business` | `cv/andrej-spirov-cv-it-business.md` | IT support, business analysis, systems roles |

Before adding a metric to a CV, record it in `cv/CV_METRICS_INTAKE.md` so it is easy to defend in an interview.

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
python3 cv/build_cv_pdf.py --all
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

After 10 or more applications, run analytics:

```bash
python3 tools/variant_performance.py
python3 tools/variant_performance.py --by source
```

## Useful commands

```bash
# Install Python requirements with uv
uv sync --all-groups

# Fallback if uv is unavailable
python3 -m pip install -r requirements.txt -r requirements-dev.txt

# Create a job file from the terminal
python3 tools/new_job.py

# Match all inbox jobs
python3 tools/batch_match_and_pack.py

# Review generated packs
python3 tools/review_packs.py --sort score

# Rebuild all CV PDFs and Canva text files
python3 cv/build_cv_pdf.py --all
```

## LinkedIn recruiter scout (optional)

Playwright-backed recruiter scouting reuses CV keyword scoring (`matching_lib`). It launches an isolated automation browser profile (see `linkedin/config.yaml`). Documentation and safeguards live in [`linkedin/README.md`](linkedin/README.md).

Default mode is review-first:

```bash
uv run python tools/recruiter_orchestrate.py daily --headed --dry-run
```

Live connection dispatch is off by default. Normal use is manual: review the
queue, open each profile, copy the approved note, and record the outcome.

CLI-click dispatch is available only if you explicitly switch the local mode to
`cli_gated` and pass the acknowledgement flag:

```bash
LINKEDIN_SEND_MODE=cli_gated uv run python tools/recruiter_orchestrate.py dispatch --headed --tier tier_1 --max 3 --allow-live-dispatch
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
uv run python tools/opportunity_orchestrate.py --config config/opportunities.example.yaml discover --dry-run

# Persist discovered rows, score them against CV variants, and report dashboard data
uv run python tools/opportunity_orchestrate.py --config config/opportunities.example.yaml discover
uv run python tools/opportunity_orchestrate.py match
uv run python tools/opportunity_orchestrate.py --config config/opportunities.example.yaml daily-queue
uv run python tools/opportunity_orchestrate.py report
```

Open the local dashboard at `/opportunities` to review saved views, inspect
evidence, generate packs for apply-ready roles, and log manual application
outcomes back to `pipeline/applications.csv`. Protected opportunity API calls use the same
`x-career-dashboard-token` header as the recruiter dashboard.

The active `Career Fresh Live Jobs` automation runs every calendar day at 09:00.
It reads only Gmail messages under the `Career/Job Alerts` label, combines those
alerts with read-only public ATS feeds, and also uses the enabled LinkedIn jobs
browser source in `config/opportunities.example.yaml`. The scheduled task uses
the existing signed-in Chrome session for LinkedIn and imports only structured
job-card/detail observations into the local pipeline. It reconciles the full
six-query browser snapshot and delivers only roles whose detail page confirms
the current live/apply signal; card-only captures are not shown. Create daily alerts on
CVBankas, CV-Online, Work in Lithuania, and LinkedIn, then route those messages
to that label. LinkedIn job URLs (`linkedin.com/jobs/view/...`) are supported
and are matched and liveness-checked like the other alert sources. Direct
LinkedIn discovery reads job-search and job-detail pages only; it does not send
messages, apply, upload CVs, or bypass a login, checkpoint, or CAPTCHA. The
standalone scraper and its separate `linkedin/.jobs-browser-profile` profile
remain available for manual use with `mode: local_profile`. If the connected
Chrome session is unavailable, the automation reports a source issue rather
than silently substituting unverified listings.
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

Older planning and optimization notes are archived under `archive/2026-05-19-cleanup/docs/`.

## Development checks

Run these exact checks before expanding automation or calling the workspace stable:

```bash
# Python checks from job-search/
uv run ruff check tools cv tests
uv run pytest -q

# Raycast extension checks
cd raycast-job-search-hub
npm test -- --run
npm run typecheck
npm run lint:ci

# Dashboard build
cd ../dashboard
npm run build
```

Use `make verify-release` from the repository root for the complete release check, or `make smoke` for a faster workflow check.


## Live dispatch approval ledger

Live connection dispatch now requires `LINKEDIN_SEND_MODE=cli_gated`, an explicit `--max 1..3`, `--allow-live-dispatch`, and a matching SQLite approval entry for the exact profile URL + note hash. The default `manual` mode blocks browser-click dispatch even when approvals exist.

```bash
make plan
make dispatch-dry
make approve-session
make check-approvals
LINKEDIN_SEND_MODE=cli_gated uv run python tools/recruiter_orchestrate.py dispatch --headed --tier tier_1 --max 3 --allow-live-dispatch
```

Generated approval state is stored under `state/` and is intentionally gitignored.


## Dashboard

* Set `CAREER_DASHBOARD_TOKEN`, then run `make dashboard-dev` and sign in at `http://127.0.0.1:3000/login`.
* Run `make dashboard-build` to validate the dashboard build.
* Run `make smoke` to exercise the full safe workflow set, including the dashboard.
