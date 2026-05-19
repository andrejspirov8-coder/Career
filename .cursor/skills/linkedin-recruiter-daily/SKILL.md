---
name: linkedin-recruiter-daily
description: >-
  Daily LinkedIn recruiter workflow using job-search tooling — recruiter_orchestrate.py phases,
  pipeline/recruiter_session_state.json for Cursor MCP browser runs, and Browse WS backend notes.
---

# LinkedIn recruiter — daily MCP + orchestrator skill

Use this when operating the Vilnius recruiter pipeline (People search → CV matcher → tiers → CSV log).

## Source of truth (repo paths)

From `Career/job-search`:

- Orchestrator CLI: [`job-search/tools/recruiter_orchestrate.py`](../../job-search/tools/recruiter_orchestrate.py)
- Matcher + notes: [`job-search/tools/recruiter_match.py`](../../job-search/tools/recruiter_match.py)
- Playwright/browse drivers: [`job-search/tools/linkedin_browser.py`](../../job-search/tools/linkedin_browser.py)
- Config + tiers + templates: [`job-search/linkedin/config.yaml`](../../job-search/linkedin/config.yaml)

Artifacts:

| File | Purpose |
|------|---------|
| `pipeline/recruiter_action_plan.jsonl` | Scout output (scores, tier, gated send flag, note text snapshot) |
| `pipeline/recruiter_session_state.json` | MCP/dispatch queue after `plan` |
| `pipeline/recruiters.csv` | Invite audit trail |

## Non-interactive day (recommended)

```bash
cd job-search

python3 tools/recruiter_orchestrate.py preflight
python3 tools/recruiter_orchestrate.py daily --headed --dry-run
python3 tools/recruiter_orchestrate.py daily --headed --dispatch-tier tier_1 --max-dispatch 1
python3 tools/recruiter_orchestrate.py followup --headed
python3 tools/recruiter_orchestrate.py report
```

`daily` chains **scout → plan → dispatch**.

## MCP / Cursor agent mode

1. Run `scout` → `plan` (or rely on freshly written JSONL):

   ```bash
   python3 tools/recruiter_orchestrate.py scout --headed
   python3 tools/recruiter_orchestrate.py plan --tier tier_1
   ```

2. Read `pipeline/recruiter_session_state.json` → each `queue[]` row has:

   - `profile_url`
   - `search_variant_slug` / `variant_slug_best`
   - `note_live_full`
   - `tier`, `primary_score`

3. Browser tools workflow (parity with Browse CLI automation):

   - Navigate to `profile_url`
   - Optionally re-run JS scrape sanity check (`linkedin_selectors.PROFILE_SCRAPER_JS`) if you mistrust staleness
   - Fill/send connection note identical to CSV note (`note_live_full` ≤ 280 chars)
   - On LinkedIn blocker (checkpoint/login wall), STOP and write `blocked_reason` into a short operator note — do **not** brute-force dialogs

4. After a manual MCP send: append `recruiters.csv` row using the bot schema (`tools/recruiter_log.py` helpers) OR re-run orchestrator dispatch in headed mode.

## Backend switch (`linkedin/config.yaml`)

- `browser.backend: playwright` → default Playwright persistent Chrome profile under `linkedin/.browser-profile`.
- `browser.backend: browse_ws` → launches Chrome + `--remote-debugging-port`, drives via Cursor **`browse`** CLI websocket (persistent profile reused).

Quit normal Chrome windows before automation starts.

## Checklist — call it “firm” only when …

1. Scout JSONL rows include all four variant slugs you care about.
2. Rows without recruiter gate NEVER show `would_send_under_matching_rules: true`.
3. `plan` preview reads sensible first names + note preview.
4. Live `--max-dispatch 1` logs `sent` in `recruiters.csv` and invitation visible in LinkedIn.

## Deferred / phase-2 scope

See [`RECRUITER_AGENT_ORCHESTRATION.md`](../../RECRUITER_AGENT_ORCHESTRATION.md) for ideas **not shipped** yet (CVbankas, Arc, Raycast, etc.).
