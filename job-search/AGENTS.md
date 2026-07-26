# Career repository agent policy

This repository contains private career data and browser-assisted workflows. Keep development-agent work local, bounded, and reviewable.

## Local-first development routing

- Check rollout state with `uv run python tools/local_dev_agents.py rollout`.
- Before the ten-run pilot completes, use local agents only when the user or Main Codex deliberately approves a typed task or proposal.
- After the exact implementer digest reaches Tier 1, route repository exploration, tests, documentation, bounded bug fixes, small UI/backend changes, and mechanical refactors through `tools/local_dev_agents.py` first.
- Tier 2 automatic application is limited to planner-created, low-risk documentation and test patches that satisfy the configured two-reviewer and size gates.
- Do not use ordinary hosted Codex subagents as a substitute for these Ollama tasks when the purpose is to conserve hosted usage.

Keep these tasks with Main Codex:

- Authentication, privacy, secrets, database migrations, dependency or lockfile changes.
- Deployment, Git history, file deletion/renaming, security policy, or agent-policy changes.
- Live LinkedIn/recruiter actions, browser profiles, and production job-search execution.
- Ambiguous architecture or any task that cannot be bounded to explicit paths and checks.

## Required local-agent flow

1. Run `make dev-agent-doctor` and stop if a required safety check fails.
2. Give the coordinator a `career_local_dev_task_v1` JSON task with explicit allowed paths and shell-free acceptance checks.
3. Inspect the coordinator-computed patch, local-review findings, and verification results. Do not rely on the model's claimed changed-file list.
4. Main Codex may record `approve --reviewed-by main-codex` only after reviewing the exact patch hash.
5. Apply only additions/modifications through the coordinator. Ask the user before deletions, renames, migrations, or other destructive work.
6. Run focused checks after application and `make verify-release` when the result is release-ready.

The weekday planner may propose work, but proposals are not authorization. A
person must approve each proposal, and no more than two implementation proposals
may be approved in one local calendar day.

## Invariants

- Never stage, commit, merge, push, reset, clean, or rewrite history without explicit user approval.
- Never pass credentials or ignored state into a local-agent task.
- Local agents may not access the internet, install packages, or run job-search/LinkedIn commands.
- Preserve unrelated dirty-worktree changes. A touched file that changed after snapshot creation makes the patch stale.
- Runtime artifacts stay under ignored `runtime/local-dev-agents/`; disposable worktrees and backups stay outside the repository.

## Cross-session memory

This project uses `.memory/` for lightweight cross-session persistence:

- **`make remember TOPIC=<topic> MSG="<message>"`** — append to a topic file
- **`make save TOPIC=<topic>`** — same, but read message from stdin (pipe-friendly)

At the end of every session, add one line summarizing what was done so the next agent session can pick up context.

Context:
- `.memory/index.md` — topic index (read this first)
- `.memory/topics/*.md` — individual topic timelines
- Full project reviews go in the Obsidian vault at `~/Documents/Obsidian Vault/Career Project Review.md`

## Verification commands

```bash
uv run ruff check tools cv tests
uv run --group dev python -m pytest -q
make dashboard-test
make raycast-check
make verify-release
```
