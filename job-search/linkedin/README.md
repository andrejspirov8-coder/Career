# LinkedIn recruiter automation (personal use)

> Safety update: live LinkedIn connection dispatch is review-first and blocked by default. Use `--dry-run` for queue review. Normal operation is manual: open the profile, copy the approved note, and record the outcome. Browser-click dispatch requires `LINKEDIN_SEND_MODE=cli_gated`, an explicit `--max 1..3`, `--allow-live-dispatch`, and a matching approval for the exact note hash.


This mini-app drives **your installed Google Chrome** via Playwright (default) or **Chrome + the Cursor `browse` CLI** when `browser.backend: browse_ws`, searches LinkedIn People for recruiters/staffers, scores each profile with **sector keywords + your CV keyword matcher** (see [`career_job_search.recruiters.matching`](../src/career_job_search/recruiters/matching.py)), and prepares short, personalized notes for human review.

Primary day driver is now **`career_job_search.recruiters.orchestrator`** (`scout` writes `pipeline/recruiter_action_plan.jsonl`, `plan` builds `pipeline/recruiter_session_state.json`, `dispatch` replays queued URLs directly). Legacy single-entry launcher: `linkedin_recruiter_bot.py` (calls the same engine).

### Orchestrator shortcuts

```bash
cd job-search
python3 -m career_job_search.recruiters.orchestrator preflight
python3 -m career_job_search.recruiters.orchestrator scout --headed
python3 -m career_job_search.recruiters.orchestrator plan --tier tier_1
python3 -m career_job_search.recruiters.orchestrator dispatch --headed --tier tier_1 --dry-run
python3 -m career_job_search.recruiters.orchestrator daily --headed --dry-run
python3 -m career_job_search.recruiters.orchestrator daily --headed --dry-run --dispatch-tier tier_1 --max-dispatch 3
python3 -m career_job_search.recruiters.orchestrator followup --headed   # wrappers around linkedin_followup.py
python3 -m career_job_search.recruiters.orchestrator report              # wraps recruiter_performance.py
```

### Agentic hiring-network workflow

`career_job_search.recruiters.hiring_network` ranks recruiters plus hiring managers, area managers,
regional managers, store directors, operations directors, HR leaders, and IT/business
leaders before dispatch. It writes a separate ranked plan and reuses the same Playwright
sender only after the safety governor approves a record.

```bash
cd job-search
source .venv/bin/activate
python -m career_job_search.recruiters.hiring_network preflight
python -m career_job_search.recruiters.hiring_network daily --headed --dry-run
python -m career_job_search.recruiters.hiring_network daily --headed --auto-send --dry-run
python -m career_job_search.recruiters.hiring_network dispatch --dry-run --tier auto_send --max 3
LINKEDIN_SEND_MODE=cli_gated python -m career_job_search.recruiters.hiring_network dispatch --tier auto_send --max 3 --allow-live-dispatch
python -m career_job_search.recruiters.hiring_network report
```

The workflow uses Pydantic schemas for strict profile/persona/CV/ranking outputs and
a **LangGraph three-agent pipeline** when `langgraph` is installed. Agents classify and rank;
only the deterministic Playwright dispatcher clicks LinkedIn controls. Blocker screens
(login, checkpoint, CAPTCHA, unusual activity) remain hard stops.

### Three-agent pipeline (web-first → validate → send)

| Agent | Tool | Output |
|-------|------|--------|
| 1 Discovery | `recruiter_web_discover.py` (+ Ollama scout) | `pipeline/candidates_discovery.csv` |
| 2 Company validate | `recruiter_company_validate.py` (+ Ollama analyst) | `pipeline/candidates_validated.csv` |
| 2b Supervisor | `recruiter_graph_workflow.py` (Ollama, review rows) | updates `candidates_validated.csv` |
| 3 Rank + dispatch | `hiring_network_workflow.py` (+ Ollama note writer) | `hiring_network_action_plan.jsonl` → `recruiters.csv` |

```bash
cd job-search
source .venv/bin/activate

# Full graph (dispatch dry-run by default)
python3 -m career_job_search.recruiters.hiring_network graph run --dry-run

# Rules-only (skip Ollama)
python3 -m career_job_search.recruiters.hiring_network graph run --dry-run --no-llm

# Full queue build with LLM notes; live send stays blocked unless cli_gated is set
python3 -m career_job_search.recruiters.hiring_network graph run --dry-run --headed --max 3

# Stage by stage
python3 -m career_job_search.recruiters.hiring_network graph run --stage discovery
python3 -m career_job_search.recruiters.company_validation
python3 -m career_job_search.recruiters.hiring_network graph run --stage rank
python3 -m career_job_search.recruiters.hiring_network graph run --stage dispatch --dry-run --max 3

# Bridge validated CSV manually
python3 -m career_job_search.recruiters.hiring_network bridge --write-action-plan
python3 -m career_job_search.recruiters.hiring_network rank
python3 -m career_job_search.recruiters.hiring_network dispatch --dry-run
```

Web research backends: `EXA_API_KEY` (Exa API) or `firecrawl` CLI. Config blocks: `web_discovery`, `company_validation` in [`config.yaml`](config.yaml). Discovery defaults to **Vilnius-only** (`geo_scope: vilnius`, `require_geo_match: true`). Offline/tests: `--backend offline`.

Human gates: review `candidates_discovery.csv` when rows have `needs_linkedin_url=true`; review `candidates_validated.csv` before rank unless `--auto-approve-review`.

### Ollama multi-agent layer (local LLM)

When `llm.enabled: true` in [`config.yaml`](config.yaml), four **local Ollama agents** enrich discovery, company validation, outreach notes, and borderline supervisor review. **Rules and Playwright dispatch stay in control** — the LLM proposes; keyword thresholds and caps decide.

**Prerequisites:**

```bash
ollama serve   # if not already running
ollama pull qwen3.5:35b-a3b-fast
ollama pull nomic-embed-text:latest
python3 -m career_job_search.recruiters.ollama_client --health
```

| Agent | Model (default) | Role |
|-------|-----------------|------|
| Discovery scout | `qwen3.5:35b-a3b-fast` | Extract names/URLs/notes from web hits (regex first) |
| Company analyst | `qwen3.5:35b-a3b-fast` | Plain-English company rationale + score blend |
| Outreach writer | `qwen3.5:35b-a3b-fast` | Polish connection notes (≤280 chars) |
| Supervisor | `qwen3.5:35b-a3b-fast` | Resolve `review` rows only (`qwen3.6:latest` for ≤5 hard cases) |
| CV embedder | `nomic-embed-text:latest` | Optional embedding blend in CV match |

Disable LLM for one run: `python3 -m career_job_search.recruiters.hiring_network graph run --no-llm --dry-run` or set `llm.enabled: false`. If Ollama is down, `fallback_to_rules: true` keeps the pipeline running on rules alone.

**Agent tracing:** add `--verbose-llm` to print each agent's input/output to the terminal, or set `llm.verbose: true` / `llm.trace: true` in config. Trace file: `pipeline/llm_trace.jsonl` (one JSON object per agent call).

**Manual mode (`LINKEDIN_SEND_MODE=manual`, default):** runs discovery, validation, ranking, and note drafting without browser-click dispatch. Use the dashboard to approve, copy notes, and record manual outcomes.

**CLI-gated mode (`LINKEDIN_SEND_MODE=cli_gated`):** only for explicitly approved small batches. It still requires an explicit `--max 1..3`, `--allow-live-dispatch`, current SQLite approval hashes, and hard stops on login wall, checkpoint, CAPTCHA, unusual activity, high failure rate, pending-invite buildup, or daily cap.

**Robustness flags (graph run):**

| Flag | What it does |
|------|----------------|
| `--no-cache` | Force fresh web search (skip `pipeline/web_search_cache.sqlite`) |
| `--no-merge-mcp` | Skip stale rows from `pipeline/mcp_discovery_batch.jsonl` |
| `--fresh-run` / `--no-fresh-run` | Clear action-plan JSONL before run (default **on** for `--full-auto`) |
| `--no-enrich` | Skip Exa/browser profile enrichment before rank |
| `--enrich-browser` | Scrape profiles with Playwright (logged-in Chrome) instead of Exa-only |
| `--only-new` / `--no-only-new` | Skip profiles already in `recruiters.csv` with status sent/pending/accepted |
| `--verbose-llm` | Log each agent call to stderr + `pipeline/llm_trace.jsonl` |

**Vilnius discovery:** `web_discovery.geo_scope: vilnius` with `geo_scope_fallback: lithuania` when a query returns hits filtered out by strict Vilnius match. `max_results_per_query: 8`, `discovery_max_rows_per_run: 40`, and expanded HR/area-manager/store-director queries in [`config.yaml`](config.yaml).

**Validation → rank:** `automation.use_validation_boost` adds score when company validation is `approved`/`review`. **Rank persona preserve:** `automation.preserve_discovery_persona` keeps discovery CSV personas (e.g. `recruiter_hr` at a software company) when the rank classifier would drop to `low_relevance`; also softens `low_cv_fit` for cross-sector HR. **`discovery_persona`** is passed through the bridge into rank.

**Profile enrichment:** after validation, Exa (or `--enrich-browser`) fills `enriched_about` / `enriched_role_text` before the supervisor agent runs.

**Daily volume (recommended):** harvest 15–25 profiles via LinkedIn People search into `pipeline/mcp_discovery_batch.jsonl`, then run graph discovery **without** `--no-merge-mcp`, plus Exa web discovery in the same run.

**Learning loop:** after `linkedin_followup.py` runs, `pipeline/persona_stats.json` is refreshed. When `automation.use_persona_stats: true`, ranking boosts personas with higher accept rates. View stats:

```bash
python3 -m career_job_search.recruiters.performance --persona-stats
python3 -m career_job_search.recruiters.hiring_network report --persona-stats
```

`dispatch --dry-run` is local-only: it previews the approved queue and final notes without
opening Chrome or visiting LinkedIn. `daily --headed --dry-run` may still open Chrome for
scouting because it needs current profile/search data, but it will not send invitations.

Artifacts:

- `pipeline/candidates_discovery.csv` — web-first discovery with profile URLs and draft rank scores.
- `pipeline/candidates_validated.csv` — company relevance pass (`validation_status`, rationale).
- `pipeline/recruiter_action_plan.jsonl` — latest scout payloads (tier, recruiter gate flags, templated notes).
- `pipeline/recruiter_session_state.json` — filtered queue Cursor agents / dispatch consume.
- `pipeline/hiring_network_action_plan.jsonl` — ranked hiring-network plan with persona, CV variant, rank score, and final note.
- `pipeline/hiring_network_run_state.json` — latest workflow state snapshot.
- `pipeline/recruiters.csv` — append-only CSV audit log (still the ground truth for accept/reply stats).

## Browser: real Chrome, not “Chrome for Testing”

By default [`config.yaml`](config.yaml) sets `browser.channel: chrome`. That launches **Google Chrome from your Mac** (the same app you use day to day), with a **separate profile folder** at `linkedin/.browser-profile/` so the bot does not touch your normal Chrome bookmarks/history.

**Before each run:** quit any **leftover automation Chrome** from a previous bot run (the window that used `linkedin/.browser-profile/`). Your normal everyday Chrome can stay open — the bot uses a separate profile folder. If launch fails with “profile already in use”, run `python3 -m career_job_search.recruiters.orchestrator preflight` to clear a stale lock.

To fall back to Playwright’s bundled Chromium (old behaviour):

```yaml
browser:
  channel: chromium
```

### Browse (`browse_ws`) backend

Keeps **`linkedin/.browser-profile/`** in sync with Playwright launches a dedicated Chrome with remote debugging (`browser.browse_debug_port`, default **9247**) and pipes commands through the **`browse`** binary (Cursor Browse plugin installs it under `.cursor/plugins/.../.bin/browse` unless `BROWSE_CLI` overrides).

**What could go wrong:** Quit every desktop Chrome session before attaching; checkpoints still require solving manually.

## Risks you accept by running it

- **LinkedIn may restrict your account** (limits on invites, temporary blocks, checkpoints). Automated outreach conflicts with LinkedIn’s normal-use expectations.
- **The UI breaks when LinkedIn ships layout changes.** You may need small edits under [`selectors.py`](../src/career_job_search/integrations/linkedin/selectors.py).
- **You are accountable for message content.** Review templates in [`config.yaml`](config.yaml).

**What could go wrong:** Your account lands on “verify identity” mid-run; invitations go to mismatched contacts if scoring thresholds are wrong; CSV/history grows on disk (local only).

## One-time setup

From the `job-search` folder:

```bash
make bootstrap
```

Install **Google Chrome** if it is not already installed: https://www.google.com/chrome/

You do **not** need `playwright install chromium` when using `browser.channel: chrome`. Only install the Playwright bundle if you switch config to `chromium`.

First run uses a **headed** browser so you can log in manually; the LinkedIn session is saved under **`linkedin/.browser-profile/`** (gitignored). That folder is Chrome profile data for the bot only—not your everyday Chrome profile.

## Sign in once (stay logged in)

The bot **does** remember LinkedIn login — but only inside its own Chrome profile folder (`linkedin/.browser-profile/`). You should **not** need to sign in on every run if that profile stays healthy.

**One-time setup (do this once):**

1. Quit extra Chrome windows (see below).
2. From `job-search/`, run:

   ```bash
   python3 -m career_job_search.recruiters.orchestrator preflight
   python3 -m career_job_search.integrations.linkedin.campaign --headed --dry-run
   ```

3. When the **automation Chrome window** opens (not Cursor’s Glass/browser panel), sign in to LinkedIn and complete any verification.
4. Wait until the terminal prints `Login check passed — continuing.`

**Each later run:** use the same commands (`--headed` or `--no-headed` after login works). Do **not** sign in again unless LinkedIn asks or you deleted `.browser-profile/`.

**Why people think login “resets” every time:**

| Cause | What to do |
|--------|------------|
| Signed in via **Cursor’s browser** (Glass / MCP) | That is a **different** session. Sign in only in the window opened by `linkedin_recruiter_bot.py` or `recruiter_orchestrate.py`. |
| **Profile locked** — previous Chrome still holding `.browser-profile` | Quit the leftover automation Chrome, or run `preflight` to clear a **stale** lock. |
| First run was **`--no-headed`** before login | Headless mode cannot complete manual login; use `--headed` once. |
| Switched `browser.channel` from `chromium` to `chrome` (or vice versa) | Rare edge case; sign in once in the new channel’s window. |
| LinkedIn **checkpoint** / unusual activity | Solve it in the automation window; the bot stops and logs `checkpoint_or_auth_url` in `recruiters.csv`. |

**Check session health:**

```bash
python3 -m career_job_search.recruiters.orchestrator preflight
```

Look for `Saved session cookies: yes` and `Profile lock: unlocked`.

## Browser modes

| Mode | How | Best for |
|------|-----|----------|
| **Playwright** (default) | `browser.backend: playwright` in config | Unattended scout + dispatch |
| **browse_ws** | `browser.backend: browse_ws` | Same automation via Chrome debug port + `browse` CLI |
| **MCP agent** | Cursor `browser_navigate` / `browser_snapshot` / `browser_fill` | Filtered People search + manual cull + send from ranked queue |
| **Browserbase** (optional) | Browse plugin `.env` with API keys | Cloud Chrome when local checkpoints persist |

MCP/Glass browser and `linkedin/.browser-profile/` are **different logins**. Sign in where you send, or use `browse_ws` so MCP and the bot share one profile.

### MCP relevance pass (recommended before live sends)

```bash
cd job-search
python3 -m career_job_search.recruiters.hiring_network rank
# MCP: filtered People search → pipeline/mcp_discovery_batch.jsonl
python3 -m career_job_search.integrations.linkedin.harvest_score pipeline/mcp_discovery_batch.jsonl --write-action-plan
python3 -m career_job_search.recruiters.hiring_network rank
python3 -m career_job_search.recruiters.hiring_network dispatch --tier queue_review --max 3 --dry-run
```

Dispatch approved rows from `pipeline/hiring_network_action_plan.jsonl` using the frozen `note` field (≤280 chars).

## Daily workflow (hiring network — recommended)

```bash
cd job-search
python3 -m career_job_search.recruiters.orchestrator preflight
python3 -m career_job_search.recruiters.hiring_network daily --headed --dry-run
python3 -m career_job_search.recruiters.hiring_network dispatch --tier queue_review --max 3 --dry-run
```

Or one command:

```bash
python3 -m career_job_search.recruiters.orchestrator daily --mode hiring_network --headed --dry-run
```

Legacy tier-only path (`scout → plan → dispatch`) still works:

```bash
python3 -m career_job_search.integrations.linkedin.campaign --headed --dry-run
```

Legacy browser-click pilot, only after switching to `LINKEDIN_SEND_MODE=cli_gated`
and approving the exact note:

```bash
LINKEDIN_SEND_MODE=cli_gated python3 -m career_job_search.recruiters.hiring_network dispatch --tier auto_send --max 1 --allow-live-dispatch
```

Default operation is manual. Open the profile, copy the approved note, send it
yourself, and record the outcome locally. Do not treat browser-click dispatch as
the normal daily path.

```bash
python3 -m career_job_search.recruiters.hiring_network dispatch --dry-run --tier queue_review --max 3
```

### Flags

| Flag | Meaning |
|------|---------|
| `--headed` | Show the browser window (recommended until stable). Use `--no-headed` for headless (experimental). |
| `--dry-run` | Search + open profiles + score + append CSV rows; never click Connect. |
| `--max N` | Override `max_connections_per_day` for this run only |
| `--variant SLUG` | Only run searches for one CV slug |
| `--browser-channel chrome` | Force installed Google Chrome (default from config) |
| `--browser-channel chromium` | Force Playwright’s downloaded Chromium |
| `--config PATH` | Alternate YAML config |

Outputs:

- **`pipeline/recruiters.csv`** — gitignored audit log ([schema](../pipeline/README.md))
- **`linkedin/run_logs/`** — screenshots when Connect cannot be found (`*-noconnect-*.png`) for debugging UI changes

### After invites: acceptance + replies (read-only)

Close the loop so you can tune thresholds against real outcomes:

```bash
cd job-search
python3 -m career_job_search.integrations.linkedin.followup --headed
```

This opens **Sent invitations** and **Messaging**, then updates `accepted_at`, `reply_at`, and `reply_excerpt` in `recruiters.csv` (best-effort heuristics; UI changes can break detection).

Weekly funnel summary:

```bash
python3 -m career_job_search.recruiters.performance
python3 -m career_job_search.recruiters.performance --by-persona
python3 -m career_job_search.recruiters.hiring_network report
```

### Pacing and caps

[`config.yaml`](config.yaml) `limits.*` controls lognormal-ish gaps between profiles, occasional feed “idle” browsing, a cool-down after each successful invite, and a **conservative daily cap** until enough sent invites show an accept rate ≥ 40% (see `max_connections_per_day_low_accept` and related keys).

### Best practices (2026 outreach safety)

These rules match what industry guides recommend and what this repo enforces in code/config:

1. **Volume:** Aim for **12–15 personalized invites per day** (not 50+). Weekly totals near **~100** are safer than one big spike; the bot’s pacemaker uses **12/day** until your logged accept rate is strong.
2. **Acceptance rate:** If accept rate in `recruiters.csv` drops below **~40%**, lower volume and tighten `matching.min_primary_score` before raising caps again.
3. **Pacing:** Keep `between_profiles_seconds_median` (~70s) and idle feed browsing — sudden bursts of clicks look automated.
4. **Hours:** Run headed during **local business hours**; avoid overnight marathons.
5. **Targeting:** Prefer **hiring ecosystem** contacts (recruiters, HR, area/store directors) via `require_recruiter_gate: true` — not generic sales ICs.
6. **Notes:** Stay under **280 characters** (LinkedIn’s limit is 300); mention *their* context, not a wall of CV text.
7. **Session:** Use **one Chrome profile** (`linkedin/.browser-profile`) — not Cursor’s Glass browser — and run `preflight` if you see profile-lock errors.
8. **Backends:** Default **Playwright + persistent Chrome** is most reliable; `browse_ws` is optional for MCP parity — quit other Chrome instances using the same profile first.
9. **Hygiene:** Run `linkedin_followup.py` weekly; withdraw stale pending invites on LinkedIn manually if your pending queue grows.
10. **Blockers:** On checkpoint/CAPTCHA, stop the bot, solve in the automation window, wait **24h** before resuming at half volume.

Sources used for these limits: [ConnectSafely 2026 limits](https://connectsafely.ai/articles/linkedin-connection-limit-per-day-guide-2026), [Linkboost automation limits](https://blog.linkboost.co/linkedin-automation-daily-limits-guidelines-2026/), [Playwright persistent context docs](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context).

## If LinkedIn shows a blocker

The bot **stops** when it detects login walls, checkpoints, CAPTCHA-ish copy, or “unusual activity” strings (see [`selectors.py`](../src/career_job_search/integrations/linkedin/selectors.py)).

1. Run again with **`--headed`**, solve the prompt in the automation Chrome window.
2. Lower daily caps/delays in [`config.yaml`](config.yaml).
3. If still stuck, wait several hours before retrying.

## Switching from Chromium to Chrome

If you previously logged in using bundled Chromium, you may need to **sign in again** once in the Google Chrome automation window—the profile format is separate.

## Tuning scoring

Raise `matching.min_primary_score` if invitations feel off-target; lower slightly if nobody passes. Prefer changing **keywords** on your CV variants in [`cv/variant_profiles.yaml`](../cv/variant_profiles.yaml); the recruiter bot reuses those lists automatically.
