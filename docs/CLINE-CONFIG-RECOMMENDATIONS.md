# Cline Configuration Recommendations

**Date:** 2026-07-28 | **Audience:** Self (for review & implementation)

---

## Overview

After a full audit of your Cline setup, here are the findings and prioritized recommendations. Your configuration is already **advanced** — you're using global `.clinerules/`, multiple MCP servers, hooks infrastructure, and project-specific contexts. The recommendations below address gaps in **security**, **reliability**, **automation**, and **scalability**.

---

## P0 — Security (Fix Immediately)

### 1.1 API Keys Hardcoded in `cline_mcp_settings.json`

**Problem:** Both `GITHUB_PERSONAL_ACCESS_TOKEN` and `FIRECRAWL_API_KEY` are stored in **plaintext** in `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`. This file is not encrypted and can be read by any process on your machine.

**Recommendation:** Use environment variables via a `.env` file or your shell profile:

1. Add to `~/.zshrc`:
   ```bash
   export GITHUB_PAT="gho_..."
   export FIRECRAWL_API_KEY="fc-..."
   ```

2. Update the MCP config to reference the env vars instead:
   ```json
   {
     "env": {
       "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PAT}",
       "FIRECRAWL_API_KEY": "${FIRECRAWL_API_KEY}"
     }
   }
   ```

   Or for Cline's format, use the variable substitution directly (Cline supports `${VAR_NAME}` in env values since v4).

3. **Alternative:** Use a 1Password CLI or `pass` integration to inject secrets at runtime.

### 1.2 Auto-Approval Audit

**Problem:** Several high-risk tools are auto-approved:

| Server | Auto-Approved Risk | Concern |
|--------|-------------------|---------|
| `desktop-commander` | `start_process`, `interact_with_process`, `kill_process`, `write_file`, `write_pdf`, `edit_block` | Full system access, arbitrary code execution, file modification |
| `firecrawl-mcp` | `firecrawl_agent` | Autonomous web research agent |
| `memory` | `read_graph`, `delete_entities`, `delete_observations`, `delete_relations` | Can destroy knowledge graph |

**Recommendation:** Remove auto-approval for destructive operations:

- `desktop-commander`: Remove `kill_process`, consider removing `start_process` + `interact_with_process` (or keep if you fully trust the model)
- `memory`: Remove `delete_entities`, `delete_observations`, `delete_relations`
- `firecrawl-mcp`: Remove `firecrawl_agent` unless you explicitly need autonomous web browsing every session

### 1.3 GitHub Token Scope

**Problem:** The PAT `REDACTED` is a fine-grained token. Verify it has **minimum required scopes** — it should only need `repo`, `pull_requests`, `issues`, `contents`. If it has admin scopes, reduce them.

---

## P1 — Architecture & Organization

### 2.1 Per-Project `.clinerules/`

**Current state:** You have a **global** `.clinerules/` at `~/Documents/Cline/Rules/` that applies to all projects.

**Gap:** The Career workspace has **no project-specific rules**. Project-specific conventions (e.g., `uv` instead of `pip`, `pytest` with specific flags, Makefile targets, pre-commit hooks order) are not codified for Cline.

**Recommendation:** Create `/Users/andrejspirov/Career/.clinerules/` with:

```
.clinerules/
├── project-context.md      # This project's tech stack, conventions, gotchas
└── workflow.md             # Custom rules for this workspace only
```

Contents for `project-context.md`:
```markdown
# Career Workspace Context

## Tech Stack
- Python 3.12+ with `uv` package manager
- TypeScript via Next.js for dashboard
- Ruff for linting + formatting
- pre-commit for local checks
- pytest with coverage for testing

## Key Conventions
- Run `make` before committing (runs lint + test)
- Use `uv` not `pip` for Python dependency management
- Python source in `job-search/src/career_job_search/`
- Tests in `job-search/tests/` using pytest
- Dashboard is in `job-search/dashboard/` (Next.js)
- CVs are markdown in `job-search/cv/`, built via `build_cv_pdf.py`
- Never commit to `job-search/inbox/` without review

## Critical Paths
- Pipeline: `job-search/pipeline/`
- Agent prompts: `job-search/linkedin/agent_prompts.yaml`
- CV variant config: `job-search/cv/variant_profiles.yaml`
- Recruiter config: `job-search/config/`
```

### 2.2 MCP Server Organization

**Current state:** MCP servers are a mix of:
- `npx -y` packages installed on-the-fly (filesystem, desktop-commander, sequential-thinking, memory, firecrawl-mcp)
- Local Node dependency (context7 at `/Users/andrejspirov/Documents/Cline/MCP/node_modules/...`)
- Local Go binary (github-mcp-server at `/Users/andrejspirov/Documents/Cline/MCP/github-mcp-server/`)

**Recommendations:**

1. **Pin versions** — `npx -y` fetches latest each time, which can break. For critical servers, either:
   - Install locally and reference the local binary: `npx -y @modelcontextprotocol/server-filesystem` → switch to local install
   - Or lock versions: `npx -y @modelcontextprotocol/server-filesystem@0.6.2`

2. **Increase `desktop-commander` timeout** — 30s is too short for complex operations like `start_process` with long-running Python scripts. Increase to 120s.

3. **Set `disabled` explicitly** — Missing `disabled` field on `filesystem`, `desktop-commander`, `sequentialthinking` means they default to `false` (enabled), which is fine, but be explicit.

4. **Context7 path** — The `context7-mcp` uses a local `node_modules` path, which is good for version stability. Consider adding a `package.json` in that MCP directory to track all local deps.

---

## P2 — Hooks & Automation

### 3.1 Populate Hooks

**Current state:** Hook directories exist but are **empty**. Cline hooks are a powerful feature for customizing behavior:

| Hook Directory | Purpose | Recommended Content |
|----------------|---------|-------------------|
| `PreToolUse` | Validate/block certain tools before execution | Check: "am I about to commit an API key?" |
| `PostToolUse` | Log or react after each tool use | Record tool usage stats for audit |
| `PreCompact` | Save critical context before compression | Dump key decisions to a file |
| `TaskStart` | Initialize session context | Load Memory Bank, set workspace vars |
| `UserPromptSubmit` | Pre-process user input | Add system-level instructions |
| `TaskComplete` | Cleanup / summary | Compress context, save final state |
| `TaskResume` | Restore context | Reload saved state |
| `TaskCancel` | Emergency cleanup | Kill stray processes, save partial state |

**Minimum viable hook setup:**

**`Hooks/TaskStart/init.sh`** (or whatever script mechanism Cline uses):
```bash
#!/bin/bash
# On task start, check if Memory Bank exists and load context
echo "[HOOK] TaskStart: Initializing session..."
```

**`Hooks/PreToolUse/guard.sh`**:
```bash
#!/bin/bash
# Block execution if dangerous pattern detected in command
# For example, prevent: `git push` without review
```

**`Hooks/TaskComplete/compress.sh`**:
```bash
#!/bin/bash
# Compact the context and save summary
```

### 3.2 Use Cline Workflows

**Current state:** `Workflows/` directory is empty.

Cline Workflows let you define reusable multi-step automation. Examples for your project:

**`Workflows/update-memory-bank.md`**:
```markdown
1. Read all files in `docs/context/`
2. Summarize decisions made in last session
3. Write updated context to `docs/context/`
```

**`Workflows/code-review.md`**:
```markdown
1. Read the diff of the current branch
2. Check for: hardcoded secrets, missing error handling, type safety
3. Run the test suite
4. Report findings
```

### 3.3 Pre-commit Hook Integration

**Current state:** Your `.pre-commit-config.yaml` is well set up (ruff, format checks, secret detection).

**Recommendation:** Add a `Cline review` step as a prepend to your commit workflow:

In `ai-workflow.md` or a local `.clinerules/workflow.md`:
```markdown
## Commit Workflow
Before `git commit`:
1. Run `make lint` (ruff)
2. Run `make test` (pytest)
3. Check for hardcoded secrets in the diff
4. Only then commit
```

---

## P3 — MCP Server Strategy

### 4.1 Build Your Custom MCP Server

**Current state:** The `docs/context/03-MCP-ARCHITECTURE.md` describes a vision for a custom `recruiter-scorer` MCP server, but it's **not implemented**.

**Recommendation:** Prioritize building the MCP server. It's the missing piece that turns your scoring engine into a composable service. Start with:

1. `job-search/mcp/server.py` — Expose `score_recruiter` tool
2. `job-search/mcp/tools.py` — Move tool implementations there
3. Register in `cline_mcp_settings.json`:
   ```json
   "local-recruiter-scorer": {
     "command": "uv",
     "args": ["run", "--directory", "/Users/andrejspirov/Career/job-search", "python", "-m", "job-search.mcp.server"],
     "timeout": 60,
     "autoApprove": ["score_recruiter"]
   }
   ```

### 4.2 Memory Server as Cross-Session Storage

**Current state:** Memory server is running but `read_graph` is auto-approved, and there's no structured usage pattern.

**Recommendation:** Use the memory server intentionally:

1. Store workspace decisions in the knowledge graph
2. Auto-approve `read_graph` only, not mutations
3. Create entities for: `project`, `decision`, `risk`, `dependency`, `team-member`
4. Create relations like: `[decision] affects [module]`, `[risk] blocked_by [dependency]`

### 4.3 Firecrawl Strategy

**Current state:** Firecrawl is fully auto-approved with a hardcoded API key.

**Recommendations:**
- Remove `firecrawl_agent` from auto-approve (it's an autonomous agent that can rack up costs)
- The `firecrawl_search` + `firecrawl_scrape` pair is excellent for web research — keep those
- Set `zeroDataRetention: true` as default for privacy
- Consider switching to the self-hosted Firecrawl instance for cost control

---

## P4 — Organization & Maintenance

### 5.1 Rules Directory Structure

**Current state:**
```
~/Documents/Cline/Rules/
├── ai-workflow.md
└── personal-preferences.md
```

**Recommendation:** Split into focused files as the rule count grows:
```
~/Documents/Cline/Rules/
├── 00-CORE.md                # Critical rules (security, response format)
├── 01-WORKFLOW.md            # Memory Bank, code review, session management
├── 02-CODING-STANDARDS.md    # TypeScript, Python, naming conventions
├── 03-MCP-USAGE.md           # How to use MCP servers effectively
├── 04-SECURITY.md            # Secrets, input validation, auth rules
└── 99-BOOTSTRAP.md           # Global instructions loaded every session
```

**Note:** Rules are read in alphabetical order. Use numeric prefixes to control precedence.

### 5.2 Backup Your MCP Config

**Current state:** There's a `cline_mcp_settings.json.bak` — good practice. But the config **contains API keys**.

**Recommendation:**
1. Never commit `cline_mcp_settings.json` to version control
2. Use `env` vars for secrets as described in §1.1
3. Keep a **template** in your project repo:
   ```json
   // .cline-mcp-settings.template.json
   {
     "mcpServers": {
       "github.com/github/github-mcp-server": {
         "env": {
           "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PAT}"
         }
       }
     }
   }
   ```

### 5.3 Periodic Cleanup Tasks

**Current state:** Multiple old task directories at `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/tasks/`:

```
1775086873597
1779231199338
1784228591942
1784257852139
1785186905809
1785187426518
```

Each contains `api_conversation_history.json` which can be **hundreds of KB**. These accumulate over time.

**Recommendation:** Add a monthly cleanup script:
```bash
#!/bin/bash
# Clean up old Cline task histories (keep last 3)
cd ~/Library/Application\ Support/Code/User/globalStorage/saoudrizwan.claude-dev/tasks/
ls -t | tail -n +4 | xargs -I {} rm -rf {}
```

---

## Summary of Action Items

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| **P0** | Move API keys to env vars | 15 min | 🔴 Critical: Security |
| **P0** | Audit + restrict auto-approvals | 10 min | 🔴 Critical: Security |
| **P0** | Verify GitHub PAT scopes | 5 min | 🔴 Critical: Security |
| **P1** | Create `.clinerules/` for Career project | 20 min | 🟡 High: Consistency |
| **P1** | Pin MCP server versions | 15 min | 🟡 High: Reliability |
| **P1** | Increase desktop-commander timeout to 120s | 2 min | 🟡 High: Reliability |
| **P2** | Populate hooks (TaskStart, PreToolUse) | 30 min | 🟢 Medium: Automation |
| **P2** | Add commit workflow to rules | 10 min | 🟢 Medium: Quality |
| **P3** | Build custom recruiter-scorer MCP server | 2-4 hrs | 🟢 Medium: Capability |
| **P3** | Use memory server intentionally | 20 min | 🟢 Medium: Context |
| **P4** | Restructure rules directory | 15 min | 🔵 Low: Organization |
| **P4** | Create MCP config template | 10 min | 🔵 Low: Maintenance |
| **P4** | Add periodic task cleanup | 5 min | 🔵 Low: Disk usage |

---

## Quick Wins (Do Now, < 5 min Each)

1. **Fix the leaked GitHub token** — Regenerate in GitHub settings, use env var
2. **Fix Firecrawl API key** — Same treatment
3. **Remove auto-approve for `delete_*` on memory server** — Prevent accidental graph corruption
4. **Increase `desktop-commander` timeout to 120s** — Avoid timeout failures on long processes
5. **Add `disabled: false` to all servers explicitly** — Self-documenting config