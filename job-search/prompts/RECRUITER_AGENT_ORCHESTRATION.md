# Recruiter automation — roadmap vs implemented scope

> Safety update: live LinkedIn connection dispatch is review-first and blocked by default. Use `--dry-run` for queue review. Non-dry-run dispatch requires `--allow-live-dispatch` after manual approval.


_Last trimmed to match repository reality (`job-search` LinkedIn recruiter stack). Older multi-tool architecture notes were aspirational._

## Implemented today

| Capability | Entry point | Outputs |
|-----------|-------------|---------|
| People search → scrape → **`match_recruiter_profile`** (single scorer) | `linkedin_recruiter_bot.py`, `career_job_search.recruiters.orchestrator scout` | `pipeline/recruiters.csv`, optionally `pipeline/recruiter_action_plan.jsonl` |
| Tier buckets from YAML | `linkedin/config.yaml` → `assign_best_tier` in `career_job_search.recruiters.matching` | Stored on JSONL scout records |
| Note builder (templates + headline/about phrase + CV anchor + keyword suffix) | `prepare_outreach_note` / `_bundle` | `note_live_full` (≤ chars from config) |
| Browser backends | **`playwright`** (default) vs **`browse_ws`** (Chrome + `browse --ws`) | Shares `linkedin/.browser-profile/` |
| Session planner for MCP / dispatch queues | `career_job_search.recruiters.orchestrator plan` | `pipeline/recruiter_session_state.json` |
| Three-agent LangGraph pipeline | `career_job_search.recruiters.hiring_network graph run` | discovery CSV → validated CSV → ranked JSONL → dispatch |
| Web-first discovery | `career_job_search.recruiters.web_discovery` | `pipeline/candidates_discovery.csv` |
| Company validation | `career_job_search.recruiters.company_validation` | `pipeline/candidates_validated.csv` |
| Dispatch from session (re-score + CSV log) | `career_job_search.recruiters.orchestrator dispatch` | CSV rows incl. dry-run previews |
| Daily chain | `career_job_search.recruiters.orchestrator daily` | scout JSONL → plan JSON → headed dispatch |

Deprecated prototype: `recruiter_agent_orchestrate.py` (removed; prints redirect to orchestrator CLI).

Detailed operator checklist + risks lives in **`job-search/linkedin/README.md`** and the Cursor skill **`.cursor/skills/linkedin-recruiter-daily/SKILL.md`**.

## Deferred (not implemented in-repo)

Ideas intentionally **out of this pass**:

- CVbankas / company-directory / Arc ingestion scouts
- Enrichment pipelines (`recruiter_index.jsonl`, auto dedup merges across sources separate from recruiters.csv)
- Raycast façade (optional fast-follow: invoke `python3 -m career_job_search.recruiters.orchestrator daily --dry-run`)
- Full message-thread parsing for follow-ups (today: best-effort heuristics in `linkedin_followup.py`)
- Cloud Browserbase / captcha offload (Browse plugin `.env` only if operator opts in)

## Historical note

Older sections of this file described many modules (`recruiter_enrich_dedup.py`, `recruiter_classify.py`, …) **that do not exist** in-tree. Prefer the Implemented table above and the tooling paths it references.
