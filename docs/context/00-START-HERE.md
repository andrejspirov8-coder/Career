# Glaze Career Command Center — Start Here

This folder is a deliberately limited context packet for building the native
Career Command Center app in Glaze.

## Folder path

`/Users/andrejspirov/Career/Glaze-Career-Command-Center-Context`

## What to attach to Glaze

Attach files `01` through `10`:

1. `01-PROJECT-OVERVIEW.md`
2. `02-JOB-SEARCH-WORKFLOW.md`
3. `03-EXISTING-DASHBOARD-SCOPE.md`
4. `04-SECURITY-RULES.md`
5. `05-opportunity_dashboard.py`
6. `06-recruiter_dashboard.py`
7. `07-opportunity-data.ts`
8. `08-recruiter-data.ts`
9. `09-opportunity-triage.ts`
10. `10-recruiter-triage.ts`

These files describe the product, safe local helper commands, data shapes, and
current triage behavior. They do not include live application records, recruiter
exports, credentials, cookies, browser profiles, or CV contents.

Do not attach anything from `.env`, `pipeline/`, `state/`, `output/`, `packs/`,
`linkedin/.browser-profile/`, or `linkedin/run_logs/`.

## Recommended clean Glaze workflow

The current Glaze attempt is in a generic two-question setup flow. Start clean
so the attachment packet is available before Glaze proposes its architecture:

1. In the current question panel, click **Dismiss** or press Escape.
2. Click **New App**. You do not need to delete the existing draft.
3. Turn on **Plan** mode. The composer should display a Plan chip.
4. Click **+**, choose **Attachment**, open this folder, and select files `01`
   through `10`.
5. Open `11-GLAZE-PLAN-PROMPT.md`, copy only the text below its
   **COPY FROM HERE** line, and paste it into the Glaze composer.
6. Submit the prompt.
7. Review Glaze's plan before approving it.

## Approve the plan only if all of these are true

- It implements **Stage 1 only** in the first build.
- It uses `/Users/andrejspirov/Career/Career-main/job-search` as the active
  source of truth.
- It never reads from or writes to `/Users/andrejspirov/Career/job-search`.
- It reuses the existing Python dashboard helpers instead of recreating the
  matching logic or importing records into a second database.
- Stage 1 is read-only and does not change career data.
- It contains no auto-apply or live LinkedIn dispatch path.
- It permanently blocks `--allow-live-dispatch`, `--full-auto`, and
  `--auto-send`.
- It does not install Homebrew, Python, uv, or other system tools without asking.
- It includes fake-data tests plus empty, malformed, missing-tool, and slow-run
  states.

If any item is missing, choose **Type what to change** in Glaze and paste:

> Revise the plan to satisfy every safety and Stage 1 acceptance requirement in
> the attached prompt. Do not build until the revised plan explicitly covers
> all of them.

## After Stage 1

Use one prompt at a time from `12-GLAZE-FOLLOW-UP-PROMPTS.md`. Do not submit all
later-stage prompts together.

