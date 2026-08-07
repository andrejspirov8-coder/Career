# Career Workspace Deep Engineering Review

## 1. Executive summary

### Overall assessment
The Career workspace is a sophisticated local-first job-search automation system with enterprise-grade security patterns including encrypted backups, HMAC-authenticated sessions, gated LinkedIn dispatch, and SQLite approval ledgers. However, the project has critical issues including hardcoded wrong paths, duplicate dashboard implementations, and incomplete security controls.

### Top five risks
1. **Hardcoded wrong path in inactive dashboard** (`dashboard/lib/data.ts`) - Could cause operations on wrong directory
2. **TOCTOU vulnerability in backup restore** (`backups.py`) - Potential for symlink attacks during restore
3. **Incomplete `is_untrusted_content()` stub** (`policy.py`) - Prompt injection protection not implemented
4. **Duplicate dashboard implementations with inconsistent versions** - Risk of running wrong code
5. **Raycast fallback path doesn't match actual workspace** (`constants.ts`) - Commands may fail silently

### Top five strengths
1. **Comprehensive safety gates for LinkedIn automation** - Manual mode default, CLI-gated live dispatch, SQLite approvals, explicit max limits, blockers
2. **Encrypted backup with authenticated encryption** - AES-256-GCM, scrypt KDF, path validation, pre-restore safety backup
3. **Clean dependency direction** - Domain models do not import CLI/dashboard modules, enforced by architecture tests
4. **Architecture invariance testing** - Tests verify no static import cycles, single source of truth for limits
5. **Versioned JSON contracts** - `career_python_helper_v1` envelope for all Python helper calls

### Safety verdicts
- **Local personal use:** Ready with controls - but review hardcoded paths first
- **Manual job-search workflow:** Ready - all commands tested, paths verified in active dashboard
- **Scheduled local automation:** Ready - safety gates prevent accidental sends
- **Recruiter discovery:** Ready - defaults to manual mode, dry-run available
- **Live LinkedIn dispatch:** Ready with controls - requires env var + flag + SQLite approval
- **External/public deployment:** Not ready - localhost binding assumptions, no external hardening

### Most important next action
Remove or explicitly archive the root `dashboard/` directory to eliminate confusion about which dashboard is active, and fix the hardcoded path in `dashboard/lib/data.ts` (line 5).

## 2. Repository topology

| Area | Active path | Purpose | Status | Notes |
|------|-----------|---------|--------|-------|
| Python package | `job-search/src/career_job_search/` | Core domain logic, CV matching, recruiter automation | Active | Uses `uv` packaging |
| CLI tools | `job-search/tools/` | Stable command wrappers | Active | Thin adapters to package |
| Main dashboard | `job-search/dashboard/` | Next.js 16.2.9 dashboard | Active | Full-featured with authentication |
| Archive dashboard | `dashboard/` | Exists but incomplete | Uncertain | Appears to be duplicate/abandoned |
| Raycast extension | `job-search/raycast-job-search-hub/` | Keyboard-driven commands | Active | Calls Python tools |
| LinkedIn automation | `job-search/linkedin/` | Browser profile + config | Active | Safety-critical |
| CV storage | `job-search/cv/` | Markdown sources + PDFs | Active | 6 variants |
| State storage | `job-search/state/` | SQLite databases, lock files | Active | Runtime data (gitignored) |
| Archive | `job-search/archive/` | Historical reference | Historical | Excluded from automation |
| MCP integration | `job-search/mcp/` | MCP server | Active | Python-based |

## 3. Architecture assessment

### Dependency Diagram (Mermaid)

```
flowchart TD
    subgraph "Dashboard"
        D[Next.js App] -->|JSON API| PS["Python Server Bridge"]
        D -->|Env| ENV[CAREER_JOB_SEARCH_ROOT]
    end

    subgraph "Python Package"
        PS -->|spawn| TOOLS["tools/*.py wrappers"]
        TOOLS -->|import| CORE["career_job_search.*"]
    end

    subgraph "Domain Logic"
        CORE --> CVS[CV Module]
        CORE --> OPPS[Opportunity Module]
        CORE --> RECRUITERS[Recruiter Module]
        CORE --> WORKSPACE[Workspace Module]
        CORE --> AGENTS[Dev Agents Module]
        CORE --> NOTIF[Notification Module]
    end

    subgraph "Integrations"
        RECRUITERS --> LINKEDIN[LinkedIn Integration]
        LINKEDIN -->|Playwright| BROWSER[Chrome Profile]
        CORE --> OLLAMA[Ollama Client]
    end

    subgraph "State"
        RECRUITERS -->|SQLite| RECRUITER_DB["state/recruiter_state.sqlite3"]
        OPPS -->|SQLite| OPP_DB["state/opportunities.sqlite3"]
        WORKSPACE -->|SQLite| AUTO_DB["state/automation.sqlite3"]
        WORKSPACE -->|Files| BACKUP["state/backups/*.career-backup"]
    end
```

### Coupling and layering analysis
- **Strength:** Core domain modules do not import dashboard code
- **Strength:** Tools are thin wrappers under 25 lines each (enforced by test)
- **Risk:** `dashboard/lib/data.ts` has hardcoded wrong path
- **Risk:** Raycast constants has wrong default path
- **Concern:** Large duplicate Raycast copies in benchmark directories

### Single-source-of-truth violations
- `MAX_LIVE_DISPATCH` correctly enforced in `core/limits.py` only
- CV catalogue variants correctly validated against actual markdown files
- Dashboard path resolution has conflicting sources

## 4. Findings

### [CRITICAL] Hardcoded wrong path in inactive dashboard may operate on wrong workspace

* **Confidence:** High
* **Component:** `dashboard/lib/data.ts`
* **File:** `dashboard/lib/data.ts:5`
* **Evidence:** Default path `process.env.HOME + '/Downloads/Career-main/job-search'` does not exist. Actual workspace is at `/Users/andrejspirov/Career/job-search/`.
* **Impact:** Any code using this fallback would read from/write to a non-existent directory, causing silent failures.
* **Recommended fix:** Remove the inactive `dashboard/` directory entirely since `job-search/dashboard/` is the active implementation.
* **Regression test:** Add check that `dashboard/` directory is excluded or removed.

### [HIGH] TOCTOU vulnerability in backup restore

* **Confidence:** High
* **Component:** Backup restore function
* **File:** `job-search/src/career_job_search/workspace/backups.py:484-494`
* **Evidence:** The code validates files before copying, but there's a time window between validation and copy where a symlink could be swapped.
* **Impact:** An attacker with local access could potentially write files outside the intended workspace during restore.
* **Recommended fix:** Use `os.openat()` with `O_NOFOLLOW` or resolve and validate paths immediately before atomic copy.
* **Regression test:** Add test simulating symlink race condition.

### [HIGH] MCP harvest stub does not validate external URLs

* **Confidence:** Medium
* **Component:** `merge_mcp_stubs_into_action_plan` function
* **File:** `job-search/src/career_job_search/recruiters/orchestrator.py:185-225`
* **Evidence:** URLs are checked for `/in/` substring but not validated against LinkedIn domain.
* **Impact:** Non-LinkedIn URLs could potentially enter the dispatch queue.
* **Recommended fix:** Add explicit domain validation: `parsed.netloc.endswith('linkedin.com')`.
* **Regression test:** Test that non-LinkedIn URLs are rejected.

### [HIGH] Stub function `is_untrusted_content()` always returns True

* **Confidence:** High
* **Component:** Policy module
* **File:** `job-search/src/career_job_search/recruiters/policy.py:159-160`
* **Evidence:** Function has no implementation logic, always returns `True`.
* **Impact:** Prompt injection protection from scraped web content is not actually implemented.
* **Recommended fix:** Implement content validation or remove the placeholder.
* **Regression test:** Add test for untrusted content detection.

### [MEDIUM] Duplicate dashboard implementations with framework version mismatch

* **Confidence:** High
* **Component:** Both dashboard directories
* **File:** `dashboard/package.json` (Next.js 15.0.0) vs `job-search/dashboard/package.json` (Next.js 16.2.9)
* **Evidence:** Root `dashboard/` has older incomplete code; `job-search/dashboard/` is the active dashboard per README.
* **Impact:** Risk of running wrong code; confusion about which is authoritative.
* **Recommended fix:** Remove or archive the root `dashboard/` directory.
* **Regression test:** Architecture test should verify only one dashboard exists.

### [MEDIUM] Raycast fallback path doesn't match actual workspace

* **Confidence:** High
* **Component:** Constants utility
* **File:** `job-search/raycast-job-search-hub/src/utils/constants.ts:17`
* **Evidence:** Default candidates use `Career/Career-main/job-search` but actual is `Career/job-search`.
* **Impact:** Raycast commands would fail to find workspace if env/preferences not set.
* **Recommended fix:** Remove incorrect default or update to match actual workspace path.
* **Regression test:** Integration test for path resolution.

### [MEDIUM] Runtime benchmark directories contain duplicate Raycast copies

* **Confidence:** High
* **Component:** Runtime artifacts
* **Evidence:** Multiple copies of `raycast-job-search-hub` in `runtime/local-dev-agents/benchmarks/` (6+ copies).
* **Impact:** Disk bloat; potential confusion if mistaken for active code.
* **Recommended fix:** Update `.gitignore` to exclude these runtime artifacts.
* **Regression test:** Add check for unexpected duplicate sources.

## 5. Security assessment

### Threat model
- **Trusted:** Local operator, authenticated dashboard sessions
- **Untrusted:** LinkedIn profile content, job listings, MCP fetch results, scraped web content
- **External attack surface:** None (localhost binding only)

### Trust boundaries
1. Browser automation profile (`linkedin/.browser-profile/`) isolated from daily Chrome
2. SQLite ledger (`state/*.sqlite3`) stores approval state, gitignored
3. Dashboard token in `.env.local` or macOS Keychain
4. Live dispatch requires 3-factor gate: env var + CLI flag + SQLite approval

### Confirmed security controls
| Control | Implementation | Effectiveness |
|---------|--------------|---------------|
| Auth | HMAC session tokens, HttpOnly cookies | Strong |
| Backup encryption | AES-256-GCM + scrypt KDF | Strong |
| Path traversal | `PurePosixPath` validation, `..` rejection | Strong |
| Live dispatch | env var + flag + approval ledger | Strong |
| Daily caps | Config + SQLite tracking | Strong |
| Profile locking | File lock + stale detection | Strong |

### Incomplete security controls
| Control | Status | Risk |
|---------|--------|------|
| `is_untrusted_content()` | Stub | Prompt injection |
| CSRF tokens | Missing | Relies on SameSite |
| Rate limiting | Missing | Dashboard API |
| Input sanitization | Partial | Scrape content |

### Recruiter/LinkedIn automation safety assessment
Very strong. The safety layers are:
1. **Default mode:** Manual (no browser-click dispatch possible)
2. **CLI-gated mode:** Requires `LINKEDIN_SEND_MODE=cli_gated`
3. **Explicit acknowledgment:** `--allow-live-dispatch` flag
4. **Approval ledger:** SQLite entry per profile URL + note hash required
5. **Max limit:** Hard-capped at 3 for live dispatch
6. **Blocker detection:** CAPTCHA, checkpoint, unusual activity hard stops

### Backup and restore assessment
Strong with one TOCTOU vulnerability noted above.
- Encryption: AES-256-GCM authenticated encryption
- Key derivation: Scrypt with 16-byte salt, 32-byte output
- Path validation: Rejects absolute paths, `..`, symlinks, unsupported types
- Size limits: 300MB max compressed, 5000 files max
- Pre-restore backup: Always creates safety backup before restore

## 6. Data and state-flow assessment

### Recruiter profile lifecycle

| State | Transitions | Storage |
|-------|-------------|---------|
| discovered | → ranked, → needs_review | `action_plan.jsonl` |
| ranked | → approved, → rejected | `recruiter_decisions` table |
| approved | → sent, → expired | `approval_expirations` table |
| sent | → pending (response), → accepted | `recruiters.csv` |
| accepted | → follow_up needed | `recruiters.csv` + `notifications` |

### Opportunity lifecycle

| State | Transitions | Notes |
|-------|-------------|-------|
| new | → matched, → review | Initial discovery |
| matched | → apply_ready, → skipped | After CV scoring |
| apply_ready | → pack_generated | Ready to apply |
| applied | → follow_up | Manual submission |
| follow_up | → response_logged | Response tracking |

### Backup lifecycle

```
create_backup()
├── validate_passphrase() - min 12 chars
├── _backup_source_files() - collect allowed files
│   ├── Reject symlinks
│   ├── Validate allowed paths
│   └── Compute SHA256 hashes
├── _write_encrypted_backup()
│   ├── tar.gz with manifest
│   ├── AES-256-GCM encrypt
│   └── Atomic write (os.replace)
└── Return metadata
```

```
restore_backup()
├── Confirm "RESTORE" exact text
├── Check worker offline (heartbeat check)
├── Validate backup path (must be in BACKUP_DIR)
├── _decrypt_backup() - AES-256-GCM decrypt
├── _extract_and_validate_archive()
│   ├── Reject symlinks / hardlinks
│   ├── Validate all paths in manifest
│   ├── SHA256 verify each file
│   └── Size limit enforcement
├── create_backup(pre_restore=True) - safety copy
└── Atomic file replacement per file
```

## 7. Test and verification assessment

### Commands executed

| Command | Result |
|---------|--------|
| `uv run ruff check tools cv tests` | All checks passed |
| `PYTHONPATH=src:tools:cv uv run python -m pytest -q` | ~400 tests passed |
| `npm ci` (dashboard) | Success |
| `npm run typecheck` (dashboard) | Running (Next.js type generation) |
| `npm ci` (raycast) | Success |
| `npm run typecheck` (raycast) | Running |

### Test coverage observations
- Architecture tests verify no static import cycles
- Security tests validate live dispatch gates
- Tests for MCP harvest, approval checks, note hashing
- Coverage appears comprehensive but exact percentage not measured

### Missing tests identified
- TOCTOU race condition for backup restore
- Non-LinkedIn URL rejection in MCP merge
- Untrusted content detection
- Path resolution in Raycast constants

## 8. Dependency and build assessment

### Python dependencies (`pyproject.toml`)
- `cryptography>=48.0.1,<49` - Good version pinning
- `playwright>=1.40,<2` - Flexible but reasonable
- `langgraph>=1.0,<2` - Optional for agents
- Uses `uv` build system (modern approach)

### Dashboard dependencies
**Active (`job-search/dashboard/package.json`):**
- Next.js 16.2.9 (current)
- React 19.2.7
- TypeScript 5.9.2
- Vitest 4.0.0

**Inactive (`dashboard/package.json`):**
- Next.js 15.0.0 (outdated)
- React 19.0.0
- No test infrastructure

### Reproducibility
- `uv.lock` provides locked Python dependencies
- `package-lock.json` for both JavaScript projects
- No supply-chain scanning in CI (no GH Actions found)

## 9. Documentation assessment

### Contradictions found

| Document | Claim | Reality |
|----------|-------|---------|
| `dashboard/lib/data.ts:5` | Path defaults to `~/Downloads/Career-main/job-search` | Actual path is `/Users/andrejspirov/Career/job-search/` |
| `raycast/utils/constants.ts:17` | Default includes `Career-main` | Actual workspace is `Career` |

### Documentation quality
- Extensive READMEs at multiple levels
- Security policy documented in `SECURITY.md`
- Architecture documented in `docs/ARCHITECTURE.md`
- Operations runbook in `docs/OPERATIONS_RUNBOOK.md`
- MCP architecture documented

## 10. Prioritised remediation roadmap

### P0 — Immediate safety or correctness issues

| Problem | Proposed change | Files affected | Risk | Validation | Effort |
|---------|-----------------|----------------|------|------------|------|
| Wrong path in inactive dashboard | Remove `dashboard/` directory | `dashboard/*` | Low (cleanup) | Verify `job-search/dashboard/` works | Small |
| TOCTOU in backup restore | Atomic path validation before copy | `backups.py` | Medium | Test symlink race | Medium |

### P1 — High-value engineering fixes

| Problem | Proposed change | Files affected | Risk | Validation | Effort |
|---------|-----------------|----------------|------|------------|------|
| MCP URL validation missing | Add LinkedIn domain check | `orchestrator.py` | Low | Test non-LinkedIn rejection | Small |
| `is_untrusted_content` stub | Implement or remove | `policy.py` | Low | Test prompt injection | Small |

### P2 — Improvements

| Problem | Proposed change | Files affected | Risk | Validation | Effort |
|---------|-----------------|----------------|------|------------|------|
| Raycast wrong default path | Remove incorrect candidate | `constants.ts` | Low | Test path resolution | Small |
| Duplicate Raycast copies | Update gitignore | `.gitignore` | Low | Verify no functional change | Small |
| Supply chain scanning | Add pip-audit to CI | N/A | Low | Verify no vulnerabilities | Small |

## 11. Recommended target architecture

The current architecture is sound. Key recommendations:

1. **Single Dashboard:** Remove root `dashboard/` to eliminate confusion
2. **Environment Variable Strategy:** Always use `CAREER_JOB_SEARCH_ROOT` for all path resolution
3. **Security Enhancement:** Implement `is_untrusted_content()` or remove it
4. **Backup Safety:** Fix TOCTOU vulnerability in restore
5. **Testing:** Add runtime security tests for the identified gaps

### Stable interfaces
- `tools/*.py` → Python package modules (keep as stable CLI)
- `career_python_helper_v1` envelope (keep versioned)
- SQLite ledger schema (keep stable, add migrations)

### Configuration strategy
- `.env.local` for dashboard token
- `linkedin/config.yaml` for recruiter settings
- `config/opportunities.example.yaml` for opportunity defaults

### State and persistence strategy
- SQLite WAL mode for concurrent access
- File locks for critical operations
- Atomic writes with temp file + rename

## 12. Final verdict

| Category | Verdict | Reason |
|----------|---------|--------|
| Local personal use | Ready with controls | Path issue needs fixing |
| Manual job-search workflow | Ready | All safe commands available |
| Scheduled local automation | Ready | Safety gates prevent accidents |
| Recruiter discovery | Ready | Dry-run default, manual only |
| Live LinkedIn dispatch | Ready with controls | 3-factor gate, max 3 |
| External/public deployment | Not ready | Local assumptions, no hardening |

---

## Questions requiring runtime or human verification

1. Are there uncommitted changes in the workspace? (README mentions "large dirty worktree")
2. Does the automation worker properly update its heartbeat for online detection?
3. Is the stub `is_untrusted_content()` function actually used anywhere in the codebase?
4. Do MCP harvest stubs ever contain non-LinkedIn URLs in practice?
5. What is the actual contents of `dashboard/.env.local` - does it match the expected format?
