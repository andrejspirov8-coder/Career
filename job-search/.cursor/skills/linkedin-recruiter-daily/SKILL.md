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

- **LangGraph driver:** [`tools/hiring_network_workflow.py`](../../../tools/hiring_network_workflow.py) (`graph run`)
- **Agent 1 — discovery:** [`tools/recruiter_web_discover.py`](../../../tools/recruiter_web_discover.py)
- **Agent 2 — company validate:** [`tools/recruiter_company_validate.py`](../../../tools/recruiter_company_validate.py)
- **Bridge CSV → scout:** [`tools/recruiter_discovery_bridge.py`](../../../tools/recruiter_discovery_bridge.py)
- **Graph nodes:** [`tools/recruiter_graph_workflow.py`](../../../tools/recruiter_graph_workflow.py)
- **Ollama client:** [`tools/recruiter_ollama_client.py`](../../../tools/recruiter_ollama_client.py)
- **Ollama agents:** [`tools/recruiter_ollama_agents.py`](../../../tools/recruiter_ollama_agents.py)
- Matcher + notes: [`tools/recruiter_match.py`](../../../tools/recruiter_match.py)
- MCP harvest scoring: [`tools/mcp_harvest_score.py`](../../../tools/mcp_harvest_score.py)
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
python3 tools/hiring_network_workflow.py graph run --dry-run --backend offline

# Or stage by stage:
python3 tools/hiring_network_workflow.py graph run --stage discovery
python3 tools/recruiter_company_validate.py
# Review pipeline/candidates_validated.csv in Sheets/Numbers
python3 tools/hiring_network_workflow.py graph run --stage rank
python3 tools/hiring_network_workflow.py graph run --stage dispatch --dry-run --max 3
```

Live sends (after CSV review and exact-note approval):

```bash
LINKEDIN_SEND_MODE=cli_gated uv run python tools/hiring_network_workflow.py graph run --stage dispatch --no-dry-run --max 3 --allow-live-dispatch
python3 tools/linkedin_followup.py --headed
python3 tools/recruiter_performance.py --by-persona
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
python3 tools/recruiter_ollama_client.py --health

# Full graph with LLM (default when llm.enabled: true)
python3 tools/hiring_network_workflow.py graph run --dry-run

# Rules-only for one run
python3 tools/hiring_network_workflow.py graph run --dry-run --no-llm

# Full automation — LLM notes + CLI-gated live LinkedIn sends
LINKEDIN_SEND_MODE=cli_gated uv run python tools/hiring_network_workflow.py graph run --full-auto --headed --max 3 --allow-live-dispatch
```

Safety: LLM never clicks Connect; Playwright does. LLM cannot alone approve sends; Ollama down → `fallback_to_rules` continues on keywords. **Full auto** skips CSV review pauses, dedupes against `recruiters.csv` (`--only-new`, default on), blocks stub/offline URLs, requires an explicit `--max 1..3`, and cannot exceed three successful sends per local calendar day.

**Robustness flags:** `--no-cache` (fresh web search), `--only-new` / `--no-only-new`, `--verbose-llm`. After followup, check learning: `python3 tools/recruiter_performance.py --persona-stats` or `report --persona-stats`.

## Daily discovery volume (Exa + MCP)

Exa web search alone often yields only a few Vilnius profiles per run. For **8–15+ candidates/day**:

1. **MCP / LinkedIn People search (15–25 profiles)** — In Cursor browser, filter Location=Vilnius and keywords from `search.queries_by_variant` or `web_discovery` (HR manager, area manager, talent acquisition, personalo vadovas). Save stubs to `pipeline/mcp_discovery_batch.jsonl` (one JSON object per line: `profile_url`, `name`, `headline`, `company`, `location`, optional `about`).

   ```bash
   # Score stubs and optionally append to action plan
   python3 tools/mcp_harvest_score.py pipeline/mcp_discovery_batch.jsonl
   ```

2. **Exa discovery** — run graph discovery **without** `--no-merge-mcp` so MCP rows merge into `candidates_discovery.csv`:

   ```bash
   python3 tools/hiring_network_workflow.py graph run --stage discovery --backend exa
   ```

3. **Inspect** `pipeline/candidates_discovery.csv` (persona, location, `needs_linkedin_url`).

Config knobs: `web_discovery.max_results_per_query` (8), `discovery_max_rows_per_run` (40), `geo_scope_fallback: lithuania`.

## Manual / MCP fill-in

When Agent 1 leaves `needs_linkedin_url=true`:

1. Use Cursor browser → find profile → append to `pipeline/mcp_discovery_batch.jsonl`
2. Re-run discovery (merges MCP batch):

   ```bash
   python3 tools/recruiter_web_discover.py --append
   ```

Bridge only (validated CSV already reviewed):

```bash
python3 tools/hiring_network_workflow.py bridge --write-action-plan
python3 tools/hiring_network_workflow.py rank
python3 tools/hiring_network_workflow.py dispatch --dry-run --max 3
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
python3 tools/hiring_network_workflow.py daily --headed --dry-run
python3 tools/recruiter_orchestrate.py daily --mode hiring_network --headed --dry-run
```
