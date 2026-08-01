# Career Workspace Workflow Rules

## Commit Workflow
Before `git commit`:
1. Run `make lint` (ruff)
2. Run `make test` (pytest)
3. Check for hardcoded secrets in the diff
4. Only then commit

## Session Start
1. Read `docs/context/INDEX.md` for current state
2. Check `PROJECT-REVIEW.md` for latest audit findings
3. Load relevant context from `docs/context/`

## MCP Usage
- Use `firecrawl_search` + `firecrawl_scrape` for web research
- Use `sequentialthinking` for complex multi-step analysis
- Use `memory` server for cross-session knowledge storage
- Use `github` server for PRs, issues, and code search
- Use `desktop-commander` for file operations and process execution