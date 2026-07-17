# Local development agents

The development-agent system delegates bounded coding work to models running
locally in Ollama. Main Codex still decides sensitive or architectural work,
reviews patches that require human judgement, and runs final release checks.

The recommended daily flow is:

`local planner -> typed proposals -> your approval -> local implementation -> local review -> checks -> Main Codex or policy approval -> safe application`

## What runs locally

- Planner, explorer, and primary reviewer: `gpt-oss:20b` in read-only mode.
- Implementer candidates: `qwen3.6:35b-a3b-coding-nvfp4`, then
  `qwen3.5:35b-a3b-coding-nvfp4`. Each exact model digest must qualify before it
  can write.
- Secondary reviewer: the qualified Qwen 3.5 model, when it is different from
  the implementer.
- Coordinator: `tools/local_dev_agents.py` using typed JSON, disposable Git worktrees, deterministic checks, and a local SQLite run log.

Both roles use a 32,768-token working context to match the running Ollama service. Keep delegated tasks bounded; split broader work into smaller tasks or have Main Codex handle it.

The whole Codex process is wrapped in a macOS sandbox. It can reach only Ollama at `127.0.0.1:11434`; the rest of the internet, the active workspace, full Git history, and the rest of the home folder are blocked. There is no online model fallback. Codex's nested tool sandbox is disabled because macOS does not permit nested Seatbelt profiles; the stricter process-wide profile remains active for Codex and every command it starts.

## First-time setup and model qualification

```bash
make dev-agent-doctor
make dev-agent-benchmark
make dev-agent-model-benchmark
make dev-agent-status
```

`doctor` checks the local binaries, exact model digests, dependencies, network
fence, and home-folder privacy fence. `dev-agent-benchmark` qualifies the first
configured implementer candidate. `dev-agent-model-benchmark` explicitly
compares Qwen 3.6 with the qualified Qwen 3.5 fallback using three small
implementation fixtures plus the fixed explorer and reviewer checks.

A model is promoted only when all cases pass, it stays inside its allowed
files, and its total runtime is no more than 1.5 times the fallback. Pulling a
new model digest automatically invalidates the old qualification until the
benchmark is rerun.

## Daily planner and proposal queue

The supervised service runs with the dashboard service. At 19:00 on weekdays
in `Europe/Vilnius`, it asks the read-only planner for up to five small,
low-risk proposals. If the computer was asleep, it performs one catch-up scan
when the service returns. It does not approve or implement proposals by itself.

From the dashboard, open **Development Agents**. Review a proposal, edit its
objective or allowed paths if needed, choose a fixed check preset, then approve
or reject it. From the terminal:

```bash
make dev-agent-plan
make dev-agent-proposals
make dev-agent-proposal-approve ID=proposal_<id>
make dev-agent-proposal-reject ID=proposal_<id>
```

At most two proposals can be approved for implementation per local calendar
day. The worker runs one model at a time. It waits for AC power before a writing
task, at least 20 GB of free disk, and any active job-search or release check to
finish.

## Run a task

Save a task under ignored `runtime/`, for example `runtime/local-task.json`:

```json
{
  "schema_version": "career_local_dev_task_v1",
  "objective": "Add focused unit tests for the opportunity URL validator without changing production behavior.",
  "role": "implementer",
  "allowed_paths": [
    "tests/test_opportunity_capture.py"
  ],
  "acceptance_checks": [
    {
      "name": "focused pytest",
      "argv": ["python", "-m", "pytest", "-q", "tests/test_opportunity_capture.py"],
      "cwd": ".",
      "timeout_seconds": 600
    }
  ],
  "risk": "low",
  "max_changed_files": 1,
  "max_diff_lines": 250
}
```

Then run:

```bash
make dev-agent-run TASK=runtime/local-task.json
make dev-agent-show ID=agent_<id>
```

Main Codex reviews the patch and can then run:

```bash
make dev-agent-approve ID=agent_<id>
make dev-agent-apply ID=agent_<id>
```

Application never stages, commits, or pushes. The coordinator first saves another recovery backup outside the repository, verifies the touched files are still fresh, and checks that the patch hash matches Main Codex's review receipt.

## Rollout and automatic application

Rollout is tied to the exact implementer model digest:

- Tier 0: explicit, approved tasks only.
- Tier 1: after 10 safe applied runs, routine eligible work becomes local-first.
- Tier 2: after a 20-run safe streak and at least 80% first-pass success across
  the pinned 20-run window, only low-risk documentation and test proposals may
  be applied automatically.

Tier 2 automatic application still requires deterministic checks, two local
reviews from different qualified models, no deletions, at most 3 files and 300
changed lines, and a planner-created proposal. A failing post-apply check causes
a safe reverse patch and pauses autonomy. Authentication, privacy, database,
dependency, deployment, Git, and live job-search changes always remain with
Main Codex.

Inspect or pause the policy at any time:

```bash
make dev-agent-autonomy
uv run python tools/local_dev_agents.py autonomy-pause --reason "manual review"
uv run python tools/local_dev_agents.py autonomy-resume
```

The rollout begins in explicit pilot mode. A run counts only when it has at
least one deterministic check and those checks pass again after application.

Open **Development Agents** in the logged-in local dashboard to:

- run the planner and review its typed proposals;
- qualify the fixed Qwen 3.6 candidate;
- queue a read-only exploration or a bounded implementation;
- choose repository paths and a fixed Python, dashboard, or Raycast check preset;
- watch the serial queue and inspect reviewer findings, check results, and the exact patch;
- pause autonomy, cancel or reject a run, or apply a patch that Main Codex already approved.

The dashboard uses this same coordinator and fixed actions. It cannot accept
arbitrary shell commands or model names. A global lock ensures that even rapid
dashboard submissions run only one Codex/Ollama model process at a time.

## Start, stop, and inspect the service

The normal managed dashboard startup also supervises the development-agent
service. For a foreground diagnostic run:

```bash
make dev-agent-service
```

Use `make dev-agent-status` or the dashboard to see the heartbeat, next planner
time, resource gates, proposal queue, model qualification, and current rollout
tier. Development notifications appear in the normal Notifications page for
new proposals, failures, automatic applications, pauses, and requalification
requirements.

All prompts, logs, patches, receipts, and the SQLite run database stay in the
ignored `runtime/local-dev-agents/` directory. Registered worktrees and recovery
backups live in dedicated sibling directories outside the repository. Runtime
artifacts are retained for 30 days.
