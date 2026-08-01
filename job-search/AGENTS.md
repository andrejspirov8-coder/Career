# Career repository agent policy

This repository contains private career data and browser-assisted workflows. Keep agent work local, bounded, and reviewable.

## Scope of agent work

Do work directly in this repository with normal tooling. Keep these tasks with the primary agent (Main Codex):

- Authentication, privacy, secrets, database migrations, dependency or lockfile changes.
- Deployment, Git history, file deletion/renaming, security policy, or agent-policy changes.
- Live LinkedIn/recruiter actions, browser profiles, and production job-search execution.
- Ambiguous architecture or any task that cannot be bounded to explicit paths and checks.

## Invariants

- Never stage, commit, merge, push, reset, clean, or rewrite history without explicit user approval.
- Never pass credentials or ignored state into automated tasks.
- Preserve unrelated dirty-worktree changes.
- Runtime artifacts stay under ignored `runtime/`; disposable worktrees and backups stay outside the repository.

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
make verify-release
```
