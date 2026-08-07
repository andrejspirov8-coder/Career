# Glaze Follow-up Prompts

Use these one at a time, only after the preceding stage passes its acceptance
checks and a stable Glaze version has been saved.

## Stage 2

> Implement Stage 2 only from the approved roadmap. Preserve the Stage 1
> layout, process runner, data adapter, safety boundaries, and tests. Add only
> the existing safe opportunity actions, clear confirmations, Activity view,
> application-pack handling, and manual application logging. Test with fake
> data first. Verify that no automatic application or CV upload path exists.
> Report exact checks and stop before recruiter functionality.

## Stage 3

> Implement Stage 3 only from the approved roadmap. Add the recruiter review
> queues, evidence inspector, note editing and 280-character validation, exact
> note approval, copying, opening LinkedIn in the default browser, manual
> outcome recording, preflight, search-and-rank, rank-existing, and dry-run
> preview. Use only the attached safe recruiter helper. Keep live LinkedIn
> dispatch permanently unavailable and block --allow-live-dispatch,
> --full-auto, and --auto-send in code and tests. Test with fake recruiter data
> before real local data. Report exact checks and stop before Stage 4.

## Stage 4

> Implement Stage 4 only from the approved roadmap. Add Applications, CV
> Library, decision-focused analytics, useful local notifications, keyboard
> navigation, command palette, accessibility, light/dark appearance testing,
> onboarding, and final privacy explanations. Do not add a cloud database,
> telemetry, auto-apply, or live LinkedIn dispatch. Run the complete end-to-end
> acceptance checklist and report every remaining limitation honestly.

## Final hardening pass

> Perform a verification-only hardening pass. Do not add features. Test the full
> user flow with fake data, empty data, malformed helper output, missing tools,
> permission denial, slow commands, unknown status values, long content, and
> cancelled operations. Confirm the legacy workspace is never accessed, career
> records are not duplicated, sensitive content is redacted from logs, and all
> forbidden dispatch or auto-apply command tokens are blocked. Fix only defects
> found by these checks, then report pass/fail for every acceptance item.
