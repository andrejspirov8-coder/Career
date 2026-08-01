---
name: linkedin-recruiter-daily
description: >-
  Daily LinkedIn recruiter workflow using job-search tooling — three-agent LangGraph pipeline,
  hiring_network_workflow.py, CSV handoffs, and Cursor MCP browser for filtered discovery.
---

# LinkedIn recruiter — three-agent pipeline skill

Use this when operating the Vilnius recruiter pipeline: **web-first discovery → company validation → rank → dispatch**.

## Source of truth (repo paths)

From the private repository root:

- **LangGraph driver:** [`hiring_network.py`](../../../src/career_job_search/recruiters/hiring_network.py) (`graph run`)
- **Agent 1 — discovery:** [`web_discovery.py`](../../../src/career_job_search/recruiters/web_discovery.py)
- **Agent 2 — company validate:** [`company_validation.py`](../../../src/career_job_search/recruiters/company_validation.py)
- **Bridge CSV → scout:** [`discovery_bridge.py`](../../../src/career_job_search/recruiters/discovery_bridge.py)
- **Graph nodes:** [`graph_workflow.py`](../../../src/career_job_search/recruiters/graph_workflow.py)
- **Ollama client:** [`ollama_client.py`](../../../src/career_job_search/recruiters/ollama_client.py)
- **Ollama agents:** [`ollama_agents.py`](../../../src/career_job_search/recruiters/ollama_agents.py)
- Matcher + notes: [`matching.py`](../../../src/career_job_search/recruiters/matching.py)
- MCP harvest scoring: [`harvest_score.py`](../../../src/career_job_search/integrations/linkedin/harvest_score.py)
- Config: [`linkedin/config.yaml`](../../../linkedin/config.yaml)

Artifacts:

| File | Purpose |
|------|---------|
| `pipeline/candidates_discovery.csv` | Agent 1 output — profile URLs, draft rank, discovery notes |
| `pipeline/candidates_validated.csv` | Agent 2 output — company relevance + `validation_status` |
| `pipeline/recruiter_action_plan.jsonl` | Scout rows bridged from validated CSV |
| `pipeline/hiring_network_action_plan.jsonl` | Ranked queue (`persona`, `rank_score`, `note`, `send_tier`) |
| `pipeline/mcp_discovery_batch.jsonl` | MCP-filtered profile stubs (merged into discovery) |
| `pipeline/recruiters.csv` | Invite audit trail |
| `pipeline/web_search_cache.sqlite` | 24h web search cache (gitignored) |
| `pipeline/persona_stats.json` | Persona accept-rate learning file |
| `pipeline/llm_trace.jsonl` | Optional agent I/O trace |

## Three-agent day (recommended)

```bash
cd job-search
source .venv/bin/activate

# Full pipeline (dry-run dispatch by default)
python3 -m career_job_search.recruiters.hiring_network graph run --dry-run --backend offline

# Or stage by stage:
python3 -m career_job_search.recruiters.hiring_network graph run --stage discovery
python3 -m career_job_search.recruiters.company_validation
# Review pipeline/candidates_validated.csv in Sheets/Numbers
python3 -m career_job_search.recruiters.hiring_network graph run --stage rank
python3 -m career_job_search.recruiters.hiring_network graph run --stage dispatch --dry-run --max 3
```

Live sends (after CSV review and exact-note approval):

```bash
LINKEDIN_SEND_MODE=cli_gated uv run python -m career_job_search.recruiters.hiring_network graph run --stage dispatch --no-dry-run --max 3 --allow-live-dispatch
python3 -m career_job_search.integrations.linkedin.followup --headed
python3 -m career_job_search.recruiters.performance --by-persona
```

Web backends (`EXA_API_KEY` or `firecrawl` CLI): set in env; config `web_discovery.backend: auto`.

## Ollama local LLM (optional enrichment)

Config block: `llm` in [`linkedin/config.yaml`](../../../linkedin/config.yaml). Default stack uses **one chat model** for the whole run to avoid slow model swaps:

| Agent | Model |
|-------|--------|
| Discovery / Company / Outreach / Supervisor | `qwen3.5:35b-a3b-fast` |
| Supervisor (≤5 hard review rows) | `qwen3.6:latest` |
| CV embedding blend | `nomic-embed-text:latest` |

```bash
ollama serve
ollama pull qwen3.5:35b-a3b-fast
ollama pull nomic-embed-text:latest
python3 -m career_job_search.recruiters.ollama_client --health

# Full graph with LLM (default when llm.enabled: true)
python3 -m career_job_search.recruiters.hiring_network graph run --dry-run

# Rules-only for one run
python3 -m career_job_search.recruiters.hiring_network graph run --dry-run --no-llm

# Full automation — LLM notes + CLI-gated live LinkedIn sends
LINKEDIN_SEND_MODE=cli_gated uv run python -m career_job_search.recruiters.hiring_network graph run --full-auto --headed --max 3 --allow-live-dispatch
```

Safety: LLM never clicks Connect; Playwright does. LLM cannot alone approve sends; Ollama down → `fallback_to_rules` continues on keywords. **Full auto** skips CSV review pauses, dedupes against `recruiters.csv` (`--only-new`, default on), blocks stub/offline URLs, requires an explicit `--max 1..3`, and cannot exceed three successful sends per local calendar day.

**Robustness flags:** `--no-cache` (fresh web search), `--only-new` / `--no-only-new`, `--verbose-llm`. After followup, check learning: `python3 -m career_job_search.recruiters.performance --persona-stats` or `report --persona-stats`.

## Daily discovery volume (Exa + MCP)

Exa web search alone often yields only a few Vilnius profiles per run. For **8–15+ candidates/day**:

1. **MCP / LinkedIn People search (15–25 profiles)** — In Cursor browser, filter Location=Vilnius and keywords from `search.queries_by_variant` or `web_discovery` (HR manager, area manager, talent acquisition, personalo vadovas). Save stubs to `pipeline/mcp_discovery_batch.jsonl` (one JSON object per line: `profile_url`, `name`, `headline`, `company`, `location`, optional `about`).

   ```bash
   # Score stubs and optionally append to action plan
   python3 -m career_job_search.integrations.linkedin.harvest_score pipeline/mcp_discovery_batch.jsonl
   ```

2. **Exa discovery** — run graph discovery **without** `--no-merge-mcp` so MCP rows merge into `candidates_discovery.csv`:

   ```bash
   python3 -m career_job_search.recruiters.hiring_network graph run --stage discovery --backend exa
   ```

3. **Inspect** `pipeline/candidates_discovery.csv` (persona, location, `needs_linkedin_url`).

Config knobs: `web_discovery.max_results_per_query` (8), `discovery_max_rows_per_run` (40), `geo_scope_fallback: lithuania`.

## Manual / MCP fill-in

When Agent 1 leaves `needs_linkedin_url=true`:

1. Use Cursor browser → find profile → append to `pipeline/mcp_discovery_batch.jsonl`
2. Re-run discovery (merges MCP batch):

   ```bash
   python3 -m career_job_search.recruiters.web_discovery --append
   ```

Bridge only (validated CSV already reviewed):

```bash
python3 -m career_job_search.recruiters.hiring_network bridge --write-action-plan
python3 -m career_job_search.recruiters.hiring_network rank
python3 -m career_job_search.recruiters.hiring_network dispatch --dry-run --max 3
```

## Acceptance checklist before live sends

- `LINKEDIN_SEND_MODE=cli_gated`, `--allow-live-dispatch`, and an explicit `--max 1..3` are present
- `candidates_validated.csv`: `validation_status` is `approved` (or you explicitly accept `review`)
- Headline/company shows **your industry** (luxury/fashion retail, multi-site ops, or IT support)
- Persona is not `low_relevance`
- `cv_variant` matches the CV you would send
- Note cites role/company/region — not generic
- On checkpoint/login wall/CAPTCHA: **STOP**

## Legacy single-chain (still supported)

```bash
python3 -m career_job_search.recruiters.hiring_network daily --headed --dry-run
python3 -m career_job_search.recruiters.orchestrator daily --mode hiring_network --headed --dry-run
```
