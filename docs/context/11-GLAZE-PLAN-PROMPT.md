# Glaze Plan Prompt

## COPY FROM HERE

Build a polished native macOS app named **Career Command Center**.

Use all attached files as authoritative project context. The attached files
describe the existing product, safe local Python helpers, data shapes, triage
behavior, and security rules. Before proposing the plan, state which attached
files you used and call out any conflict between them.

### Working mode

I am sending this in Plan mode. Do not write code in your first response.

1. Return a staged plan covering architecture, screens, data flow, safe command
   contracts, edge cases, verification, and risks.
2. Separate facts found in the attachments from your assumptions.
3. Ask no more than two questions, only if genuinely blocking.
4. After I approve the plan, implement **Stage 1 only**. Later stages are not
   authorized yet.
5. Save a stable Glaze version after each completed stage.

### Product goal

Create a calm, fast, local-first career operations app for one user in Vilnius.
Local-first means career records stay on the Mac.

The app should turn the existing Python tools, local files, Raycast workflows,
and web dashboard into one excellent native Mac experience. It is a native
control center over the existing backend, not a generic kanban tracker, skills
journal, networking CRM, or website wrapped in a desktop window.

The daily flow should take about 10–15 focused minutes:

1. See today's highest-value actions.
2. Review the best current job opportunities.
3. Understand why each role matches a particular CV.
4. Prepare and reveal an application pack.
5. Open the source listing and apply manually.
6. Record the application and later outcome.
7. Review recruiter candidates and outreach notes.
8. Open LinkedIn, act manually, and record the result.
9. See which CV variants, sources, and activities lead to replies and interviews.

### Source of truth and ownership

The only active workspace is:

`/Users/andrejspirov/Career/Career-main/job-search`

The following folder is an old reference copy and must never be read from,
modified, or offered as a fallback:

`/Users/andrejspirov/Career/job-search`

The existing backend already handles CV variants, PDF generation, opportunity
discovery and live checks, job-to-CV matching, evidence and explanations,
application packs, opportunity state, recruiter ranking, note drafting,
approvals, audit history, application tracking, and performance reporting.

Do not rewrite or duplicate that logic. Do not migrate career records into a
second database. Do not modify the existing Python source, CSV schemas, SQLite
structures, configuration, CV files, or Next.js dashboard. Use the dashboard as
a behavior reference, not as the new visual shell.

### Runtime architecture

Build a native Mac interface over the existing Python helpers.

On first launch:

- Try the active path above.
- Validate that `tools/opportunity_dashboard.py` and
  `tools/recruiter_dashboard.py` exist.
- If validation fails, show a native folder picker.
- Store only the chosen folder and UI preferences in the app's private data.
- Provide **Validate Workspace** in Settings.

Run helpers with the chosen job-search folder as the working directory. Use a
safe process API with an argument array. Never interpolate user-controlled text
into a shell command.

Initial read contracts:

- `uv run python tools/opportunity_dashboard.py overview`
- `uv run python tools/opportunity_dashboard.py detail --opportunity-id <id>`
- `uv run python tools/opportunity_dashboard.py weekly-roi`
- `uv run python tools/recruiter_dashboard.py overview`

They return JSON shaped as `{"ok": true, "data": ...}`.

Create one adapter layer that:

- Runs helpers away from the main UI thread.
- Parses and validates JSON instead of trusting process exit code alone.
- Converts errors into plain-English messages with a useful next step.
- Prevents the same long-running action from starting twice.
- Supports cancellation where practical.
- Shows progress, elapsed time, completion, and safe output.
- Redacts credentials, cookies, CV contents, and private note text from logs.
- Refreshes affected data after successful actions.
- Watches relevant local files and debounces repeated changes.
- Does not require a local web server or a new cloud service.

Do not require MCP at runtime. Do not install Homebrew, uv, Python, or other
system dependencies without explicit user permission. If something is missing,
diagnose it and show the exact setup step.

### Complete product structure

Plan these sidebar destinations:

1. Today
2. Opportunities
3. Recruiters
4. Applications
5. CV Library
6. Analytics
7. Activity
8. Settings

#### Today

Make Today the default decision screen. Show Top 5 live opportunities, Apply
Today, roles closing soon, applications missing outcomes, follow-ups due,
recruiter notes awaiting review, health warnings, last refresh, and one clearly
recommended next action. Avoid a wall of statistics.

#### Opportunities

Use a native three-pane flow: saved views, a compact opportunity list, and a
detail inspector.

Saved views should include Top 5 Today, Fresh Live, Apply Today, Needs Review,
Needs CV Tailoring, Closing Soon, Follow Up, Missing Outcome, Risk Flags,
Applied, and Skipped.

Rows show title, company, location, source, fit score, recommended CV, status,
live status, deadline, and a risk indicator.

The detail inspector shows source link, company/role/location evidence,
live-check evidence, best and runner-up CV, fit and component scores,
confidence, a plain-English match explanation, keyword hits and gaps, risk
flags, pack files, and action history. Load full descriptions and evidence only
after selection.

#### Recruiters

Use the same list-and-detail pattern. Saved views: Needs Review, Suggested
Candidates, Approved Notes, Risk Flags, Sent, and Skipped.

Rows show name, headline, company, location, persona, CV variant, rank score,
decision, approval state, status, and risks. The inspector shows evidence,
scoring explanation, the draft note, 280-character validation, note-hash and
approval state, action history, and next action.

#### Applications

Use the real fields described by the attachments: date, company, title, CV
variant, source, outcome, deadline, match score and confidence, salary,
tailored-CV flag, response date, opportunity ID, pack folder, application URL,
and notes. Include active, follow-up, interview, rejected, and missing-outcome
views.

#### CV Library

Support the six active variants: luxury-retail, luxury-retail-lt,
operations-management, operations-management-lt,
business-process-operations, and it-business.

Show intended role family, source Markdown, visual PDF, ATS PDF, timestamps,
and missing outputs. Only open or reveal files until a later approved stage.

#### Analytics

Show decision-useful evidence: applications by status, interview and reply
rates, outcomes by CV variant and source, average response time, match score
versus interview outcome, recruiter results by persona, overdue follow-ups, and
a plain-English summary based only on recorded data. For small samples, show
**Not enough data yet** instead of unstable percentages.

#### Activity and Settings

Activity shows the active run, recent successes and failures, timestamps, safe
output, retry, and reveal-log actions.

Settings shows workspace path, validation, uv and Python availability,
read-only versus safe-actions mode, notifications, appearance, privacy, and
permanently blocked operations.

### Safe actions for later approved stages

Use only actions exposed by the attached safe helpers.

Opportunity actions: `mark_review`, `mark_skipped`, `mark_apply_ready`,
`generate_pack`, `mark_applied`, `log_application`, and `snooze_followup`.

Recruiter run actions: `preflight`, `search_rank`, `rank_existing`, and
`dispatch_dry_run`.

Recruiter review actions: approve or update a note, mark review or skipped,
bulk review or skip, record note copying, record a manual send, mark pending,
replied, accepted, or rejected, and snooze follow-up, using the exact helper
contracts in the attachments.

For every state-changing action, show what will change, confirm file creation or
final outcomes, disable the control while running, validate JSON, show success
or failure, and refresh afterward.

### Permanent safety boundaries

The app must never:

- Apply to a job or upload a CV automatically.
- Send a LinkedIn invitation or message.
- Expose live LinkedIn dispatch.
- Run a command containing `--allow-live-dispatch`, `--full-auto`, or
  `--auto-send`.
- Bypass approval, note hashes, CAPTCHA, checkpoints, or account warnings.
- Read from or write to the legacy workspace.
- Store passwords, cookies, sessions, or tokens in plain text.
- Display secrets or full private content in logs.
- Send career records to telemetry or analytics services.
- Silently modify a CV, matching rule, or data schema.
- Silently install software.

The app may prepare, explain, open, copy, and record. The user performs all job
applications and LinkedIn actions manually.

### Visual direction

Make this feel like a high-quality native productivity app:

- Native macOS sidebar, compact lists, and inspector.
- Calm information density inspired by Things and Linear.
- Fast keyboard flow inspired by Raycast.
- System typography and native controls.
- System, light, and dark appearances.
- Charcoal and deep-green surfaces with restrained teal `#2DD4BF`.
- Amber only for warnings and red only for errors or genuine risk.
- Prefer hierarchy, spacing, and dividers over large card grids.
- Avoid giant KPI tiles, excessive pills, glossy gradients, and marketing UI.
- Use SF Symbols consistently and maintain accessible contrast.
- Let long content wrap without breaking the layout.

Plan Command-K, Command-R, Command-1 through Command-8, arrow navigation,
Return, and Escape. Do not register a global shortcut until the app is stable.

### Edge cases

Design explicit states for no data, a moved workspace, permission denial,
missing uv/Python/dependencies, empty or malformed files, invalid helper JSON,
`{"ok": false}`, slow/cancelled/duplicate/partial runs, stale live checks,
closed or duplicate roles, missing URLs/packs/PDFs, very long content, unknown
future status values, recruiter notes over 280 characters, edits invalidating an
approval, browser checkpoints or warnings, and too little data for analytics.

Never show a blank screen. Explain the state and offer a useful next step.

### Build stages

#### Stage 1 — Read-only foundation

This is the only stage authorized after plan approval:

- Native shell and sidebar.
- Workspace validation and folder picker.
- Safe process runner and data adapter.
- Today.
- Read-only Opportunities with saved views, search, filters, list, and lazy
  detail.
- Open a listing in the default browser.
- Reveal an existing pack or PDF in Finder.
- Refresh and debounced file watching.
- Loading, empty, stale, and error states.
- Fake-data preview for safe tests.
- No career-data writes.

#### Later roadmap, not yet authorized

- Stage 2: safe opportunity actions, Activity, packs, and manual application
  logging.
- Stage 3: recruiter review, note editing/approval/copying, manual outcomes,
  preflight, ranking, and dry-run preview only.
- Stage 4: Applications, CV Library, analytics, useful notifications, keyboard
  navigation, accessibility, and final polish.

### Stage 1 acceptance checklist

Stage 1 is complete only when:

- The active workspace validates or I can choose another folder.
- Real helper data loads into Today and Opportunities.
- Saved views, search, filters, selection, and lazy detail work.
- I can open a source listing and reveal an existing local file.
- Empty, malformed, missing-tool, and slow states are understandable.
- Fake fixtures test success, empty, and failure paths without private data.
- Long content and keyboard-only navigation work.
- Stage 1 performs no career-data writes.
- No path can apply to jobs or dispatch LinkedIn actions.
- No private content appears in diagnostics.

For every stage, test with fake data first, report the exact checks and pass/fail,
list limitations honestly, and do not call a stage complete while a required
check is failing.

Now return the plan only. Do not write code yet.

