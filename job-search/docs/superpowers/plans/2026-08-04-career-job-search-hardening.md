# Career Job-Search Reliability and Security Hardening Implementation Plan

> **For agentic workers:** Use subagent-driven-development when independent task dispatch is available; otherwise execute the checklist sequentially in the current session. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local career job-search workspace safe to operate, deterministic to test, strict about configuration and timestamps, reliable across opportunity sources, and internally consistent from authentication through release verification.

**Architecture:** Keep the application local-first: SQLite remains the only supported runtime persistence layer, while the unapproved Supabase migration path is disabled and treated as a separate future design. Use one local dashboard/API access model: a required bearer token for service calls and a signed, expiring, HttpOnly dashboard session cookie for browser navigation; no cookie is trusted merely because it exists. Keep source adapters behind one retry/fetch contract, normalize configuration before runtime dispatch, and keep matching/orchestration rules in Python rather than duplicating them in the dashboard.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLite, `httpx`, PyYAML, pytest, Ruff, Next.js 16.2, React 19, TypeScript, Vitest, jsdom, Playwright, npm, GitHub Actions, and shell tooling compatible with macOS.

## Global Constraints

* Preserve every pre-existing dirty-worktree change; do not reset, clean, stage, commit, merge, push, or rewrite history without explicit user approval.
* Do not pass `.env*`, ignored `state/`, browser profiles, runtime artifacts, or other ignored state to subagents or external services.
* Treat `/Users/andrejspirov/Career/job-search` as the only write target; do not use adjacent historical Career copies.
* The current worktree is dirty and contains unrelated modifications, deletions, and untracked files. Establish a patch/status snapshot before implementation and compare against it before every final claim.
* `CAREER_DASHBOARD_TOKEN` must be configured for protected API access; missing configuration must fail closed with a configuration error, never with a development fallback.
* Browser authentication must require a valid signed session or a valid explicit dashboard-token header; the presence of an arbitrary cookie is never sufficient.
* `CAREER_ALLOW_LOCAL_SIGNUP` defaults to disabled. Enabling local account creation requires both a valid dashboard authentication result and a same-origin request.
* Local SQLite under `state/` remains the supported persistence architecture. Do not execute, apply, or live-validate the Supabase migration during this plan.
* External opportunity sources, browser automation, LinkedIn access, and live recruiter actions remain explicit opt-in operations. Tests must use fixtures or mocked network calls.
* Configuration validation must use canonical runtime source names, reject unknown fields in bounded models, and validate every enabled source before discovery starts.
* `--since` filtering must compare parsed timezone-aware instants. It must not use `startswith()`, lexicographic string comparison, status shortcuts, score shortcuts, or `match is None` shortcuts.
* Salary parsing must have one shared implementation for matching and preferences, with annual/monthly normalization, ranges, European separators, `k` notation, and `m` notation.
* Dependency or lockfile changes require explicit approval. This includes `dashboard/package.json`, `dashboard/package-lock.json`, `pyproject.toml`, and `uv.lock`.
* Deletion, renaming, quarantine, migration, security-policy, deployment, and GitHub-settings changes require explicit approval. The plan identifies them but does not silently perform them.
* Every implementation task follows test-first sequencing: add or amend a deterministic failing test, run the narrow test, implement the smallest change, rerun the narrow test, then run the relevant broader suite.
* No task may claim completion until its named verification command has been run and its result recorded.

---

## Recommended decisions and approval gates

The following decisions make the repository coherent without expanding scope:

* **Persistence:** retain local SQLite and document Supabase artifacts as dormant, unsupported design material. Disable the malformed migration helper rather than repairing a remote database path that conflicts with `docs/ARCHITECTURE.md` and `docs/SCHEMAS.md`.
* **Dashboard/API authentication:** use `CAREER_DASHBOARD_TOKEN` as the only local access credential. The browser receives a signed session cookie after the token is validated; the FastAPI bridge always sends the configured token and never forwards a Supabase cookie or an empty bearer value.
* **Account endpoints:** keep the existing local user-store code only as a separately bounded account subsystem. It does not grant dashboard/API access in this release. Local signup is disabled by default and, when explicitly enabled, is owner-authenticated.
* **Configuration:** make the example configuration local-safe with inbox discovery enabled and all network/browser sources disabled. A user must opt into each external source.
* **Source reliability:** keep the public source wrapper names, but make them all use the shared `httpx` fetch contract and a thread-safe per-source rate limiter.

The following owner actions are prerequisites, not autonomous agent actions:

* Revoke and rotate the exposed Supabase service-role credential found in the migration helper and the ignored local environment file. Do not print the value while doing so.
* Rotate `CAREER_DASHBOARD_TOKEN` if it has ever been shared outside the local machine, then set a separate `CAREER_DASHBOARD_SESSION_SECRET` with at least 32 random characters.
* Confirm that the Supabase migration is not required for any deployed or scheduled workflow before the helper is disabled and the dormant artifacts are quarantined or removed.
* Approve any deletion or relocation of `supabase/migrate_private.py`, `supabase/migrations/20260804_private_job_scan_schema.sql`, `config/opportunities.example.yaml.bak`, or `config/opportunities.yaml.new`.
* Approve any dashboard ESLint dependency and lockfile repair.

## File map

The implementation should stay bounded to the following units:

* `src/career_job_search/api/auth.py` owns the FastAPI bearer-token boundary and must contain no legacy token or implicit JWT fallback.
* `src/career_job_search/api/routers/auth.py` owns account endpoint policy; it must not turn optional account login into dashboard authorization.
* `dashboard/lib/server/session.ts` owns signed-session creation and verification.
* `dashboard/lib/server/auth.ts`, `dashboard/lib/dashboard-page-auth.ts`, and `dashboard/proxy.ts` consume the session verifier and the explicit token verifier; they must not duplicate cookie-presence checks.
* `dashboard/lib/server/fastapi-bridge.ts` owns server-to-server authorization headers and must fail before `fetch()` if the backend token is absent.
* `src/career_job_search/opportunities/config_validation.py` owns canonical configuration parsing and normalization.
* `src/career_job_search/opportunities/orchestrator.py` consumes the normalized configuration and owns strict `--since` selection.
* `src/career_job_search/core/http_client.py` owns retry, timeout, response handling, and shared rate-limit primitives.
* `src/career_job_search/opportunities/sources.py` owns source registration, collection, deduplication, and compatibility wrappers; obsolete urllib retry code must not remain there.
* `src/career_job_search/opportunities/salary.py` owns shared salary parsing and monthly normalization.
* `src/career_job_search/opportunities/matching.py` owns fit scoring and calls the shared salary module.
* `src/career_job_search/opportunities/preferences.py` calls the same salary module rather than maintaining a second parser.
* `supabase/migrate_private.py` becomes a fail-closed dormant stub unless the owner approves a separate remote-persistence project.
* `docs/ARCHITECTURE.md`, `docs/SCHEMAS.md`, `docs/OPERATIONS_RUNBOOK.md`, `README.md`, and `docs/REQUIRED_CHECKS.md` must describe the same local-first architecture and command names.

## Task 1: Establish the worktree baseline and complete security decisions

**Files:**

* Create outside the repository: `../job-search-baseline-20260806.status`
* Create outside the repository: `../job-search-baseline-20260806.patch`
* Inspect only: `AGENTS.md`, `.gitignore`, `docs/ARCHITECTURE.md`, `docs/SCHEMAS.md`
* Owner action: ignored `.env.local`, Supabase project credentials, dashboard runtime environment

**Interfaces:**

* Produces a status snapshot and binary patch that later tasks use to distinguish planned changes from pre-existing dirty work.
* Produces explicit owner decisions for credential rotation, dormant Supabase artifacts, signup policy, and dependency changes.

* [ ] **Step 1: Capture the current tracked and untracked state without modifying it.**

    ```bash
    cd /Users/andrejspirov/Career/job-search
    git status --short > ../job-search-baseline-20260806.status
    git diff --stat >> ../job-search-baseline-20260806.status
    git diff --binary > ../job-search-baseline-20260806.patch
    git ls-files --others --exclude-standard >> ../job-search-baseline-20260806.status
    ```

    Expected outcome: the snapshot records the existing dirty files and the patch is stored outside the repository. No index, working-tree, or ignored file changes occur.

* [ ] **Step 2: Confirm that the existing release lock is preserved.**

    ```bash
    test -d runtime/release-check.lock && printf '%s\n' 'existing release lock preserved' || true
    ```

    Expected outcome: an existing lock directory is reported if present; it is not removed, recreated, or passed to an agent.

* [ ] **Step 3: Record the known baseline failures without treating them as regressions.**

    ```bash
    uv run ruff check src cv tests || true
    uv run --group dev python -m pytest -q || true
    (cd dashboard && npm test) || true
    (cd dashboard && env -u NODE_ENV npm test)
    (cd dashboard && npm run typecheck)
    (cd dashboard && npm run build)
    make verify-release || true
    ```

    Expected outcome: preserve the already observed baseline: Ruff has findings, Python has the architecture and contract-pipeline failures, normal dashboard tests fail under inherited production settings, the explicit `env -u NODE_ENV` dashboard suite passes, typecheck/build pass, and the release gate stops at the macOS `mktemp` failure. The `|| true` commands are diagnostic only and do not constitute success.

* [ ] **Step 4: Rotate the exposed credentials through their providers without displaying them.**

    Owner action: revoke the Supabase service-role key, issue a replacement, remove the old key from ignored local environment files, and rotate `CAREER_DASHBOARD_TOKEN` if necessary. Verify the old service-role credential cannot authenticate. Do not run `supabase/migrate_private.py` before this action.

* [ ] **Step 5: Approve the recommended architecture decisions.**

    Owner action: confirm local SQLite persistence, token-only dashboard access with signed browser sessions, disabled-by-default signup, disabled-by-default external sources, and dormant Supabase artifacts. If any decision changes, stop before Task 2 and create a separate bounded design plan rather than combining incompatible models.

## Task 2: Replace permissive authentication with one validated local model

**Files:**

* Create: `dashboard/lib/server/session.ts`
* Modify: `src/career_job_search/api/auth.py`
* Modify: `src/career_job_search/api/routers/auth.py`
* Modify: `dashboard/lib/server/auth.ts`
* Modify: `dashboard/lib/dashboard-page-auth.ts`
* Modify: `dashboard/proxy.ts`
* Modify: `dashboard/lib/server/fastapi-bridge.ts`
* Modify: `dashboard/app/(dashboard)/api/auth/login/route.ts`
* Modify: `dashboard/app/(dashboard)/api/auth/logout/route.ts`
* Modify: `dashboard/app/(dashboard)/api/auth/signup/route.ts`
* Modify: `dashboard/lib/dashboard-auth.test.ts`
* Modify: `dashboard/proxy.test.ts`
* Create: `dashboard/lib/server/session.test.ts`
* Create: `dashboard/lib/server/fastapi-bridge.test.ts`
* Modify: `tests/test_api_server.py`
* Create: `tests/test_api_auth.py`

**Interfaces:**

* `dashboard/lib/server/session.ts` exports:

    ```typescript
    export type DashboardSessionClaims = {
      version: 1
      subject: 'local-user'
      expiresAt: number
    }

    export function createDashboardSession(
      secret: string,
      claims: DashboardSessionClaims,
    ): string

    export function verifyDashboardSession(
      value: string | null | undefined,
      secret: string,
      nowMs?: number,
    ): DashboardSessionClaims | null
    ```

* `dashboard/lib/server/auth.ts` exports one request-level decision function used by proxy, page auth, and API routes. It must validate either the explicit dashboard token header or the signed session cookie, and it must return `503` when required server configuration is missing.
* `dashboard/lib/server/fastapi-bridge.ts` exports `dashboardBackendAuthHeaders(env?: NodeJS.ProcessEnv): Record<string, string>`. It returns `Content-Type` plus `Authorization: Bearer <configured-token>` and throws before any network request when the token is absent.
* `src/career_job_search/api/auth.py` exports `verify_token` as the sole protected FastAPI dependency. It accepts only `Bearer <CAREER_DASHBOARD_TOKEN>`, sets `current_user_id` to `local-user`, and rejects JWT-looking tokens unless they exactly equal the configured local token.

* [ ] **Step 1: Add failing signed-session tests before changing authentication code.**

    Add tests to `dashboard/lib/server/session.test.ts` for:

    ```typescript
    it('round-trips a signed local session', () => {
      const token = createDashboardSession('a'.repeat(32), {
        version: 1,
        subject: 'local-user',
        expiresAt: 2_000,
      })
      expect(verifyDashboardSession(token, 'a'.repeat(32), 1_000)).toMatchObject({
        subject: 'local-user',
        expiresAt: 2_000,
      })
    })

    it('rejects tampering, expiry, a wrong secret, and an arbitrary cookie value', () => {
      const token = createDashboardSession('a'.repeat(32), {
        version: 1,
        subject: 'local-user',
        expiresAt: 2_000,
      })
      expect(verifyDashboardSession(`${token}x`, 'a'.repeat(32), 1_000)).toBeNull()
      expect(verifyDashboardSession(token, 'a'.repeat(32), 2_000)).toBeNull()
      expect(verifyDashboardSession(token, 'b'.repeat(32), 1_000)).toBeNull()
      expect(verifyDashboardSession('e2e-token', 'a'.repeat(32), 1_000)).toBeNull()
    })
    ```

* [ ] **Step 2: Run the session tests and confirm they fail because the new interface is absent.**

    ```bash
    cd /Users/andrejspirov/Career/job-search/dashboard
    NODE_ENV=test npx vitest run lib/server/session.test.ts
    ```

    Expected outcome: failure identifying the missing session module or exports; no existing authentication behavior is changed by this step.

* [ ] **Step 3: Implement the minimal HMAC session codec.**

    In `dashboard/lib/server/session.ts`, encode a versioned JSON claims payload using base64url and append an HMAC-SHA256 signature over the encoded payload. Verify the exact two-part format, JSON shape, version, subject, numeric future expiry, and signature using constant-time comparison. Reject empty secrets, malformed base64url, altered payloads, altered signatures, expired claims, and unknown versions. Do not include the raw dashboard token in the cookie.

* [ ] **Step 4: Run the session tests and confirm they pass.**

    ```bash
    NODE_ENV=test npx vitest run lib/server/session.test.ts
    ```

    Expected outcome: all session round-trip and rejection tests pass.

* [ ] **Step 5: Add failing Python API boundary tests for missing configuration and legacy rejection.**

    Add tests to `tests/test_api_auth.py` that assert:

    ```python
    def test_missing_dashboard_token_fails_closed(monkeypatch):
        monkeypatch.delenv("CAREER_DASHBOARD_TOKEN", raising=False)
        response = TestClient(create_app()).get(
            "/api/v1/me", headers={"Authorization": "Bearer local-dev"}
        )
        assert response.status_code == 503

    def test_supabase_jwt_is_not_an_api_fallback(monkeypatch):
        monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "expected-token")
        response = TestClient(create_app()).get(
            "/api/v1/me",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.fake.signature"},
        )
        assert response.status_code == 403
    ```

    Add authenticated signup tests proving that the endpoint returns `403` when `CAREER_ALLOW_LOCAL_SIGNUP` is absent or false, returns `401`/`503` without bearer authentication, and succeeds only when both the feature flag and the valid bearer token are present.

* [ ] **Step 6: Run the new Python auth tests and confirm the permissive behavior fails them.**

    ```bash
    uv run --group dev python -m pytest -q tests/test_api_auth.py tests/test_api_server.py
    ```

    Expected outcome: the tests expose the `local-dev` fallback, Supabase-JWT fallback, and unguarded signup behavior before implementation.

* [ ] **Step 7: Make FastAPI authentication fail closed.**

    In `src/career_job_search/api/auth.py`:

    * remove `LEGACY_TOKEN`;
    * remove `_is_supabase_jwt` and `_verify_supabase_jwt` from the protected-token path;
    * return `503` with `CAREER_DASHBOARD_TOKEN is not configured.` when the expected token is empty;
    * retain strict `Bearer` parsing and constant-time comparison;
    * return `403` for a configured but invalid token;
    * set `current_user_id` to `local-user` only after successful comparison.

    In `src/career_job_search/api/routers/auth.py`, add the `verify_token` dependency to `/api/v1/auth/signup` and gate it behind `CAREER_ALLOW_LOCAL_SIGNUP=true`. Keep the local user store bounded to account management; it must not be used as an implicit dashboard session. Remove the Supabase access token from the dashboard-facing response contract so a Supabase token cannot be mistaken for a valid local API bearer token. Do not remove the `supabase` dependency or edit `uv.lock` in this task without the dependency approval gate.

* [ ] **Step 8: Add failing dashboard tests for cookie validation and empty bridge credentials.**

    Update `dashboard/lib/dashboard-auth.test.ts` and add `dashboard/lib/server/fastapi-bridge.test.ts` for these cases:

    * a valid signed cookie authorizes a page/API request;
    * `career_dashboard_session=arbitrary` returns `401`;
    * an expired or wrong-secret cookie returns `401`;
    * the old `career_sb_token` cookie never authorizes a request;
    * a valid token header still authorizes a non-browser client;
    * an empty `CAREER_DASHBOARD_TOKEN` produces `503` rather than `Authorization: Bearer `;
    * the bridge never reads a Supabase cookie.

* [ ] **Step 9: Implement one dashboard authorization path.**

    In `dashboard/lib/server/auth.ts`:

    * replace `DASHBOARD_SESSION_SUPABASE_TOKEN_COOKIE` with `DASHBOARD_SESSION_COOKIE = 'career_dashboard_session'`;
    * add `CAREER_DASHBOARD_SESSION_SECRET` loading and require at least 32 non-whitespace characters;
    * validate the explicit `x-career-dashboard-token`/Bearer header against `CAREER_DASHBOARD_TOKEN`;
    * otherwise validate `DASHBOARD_SESSION_COOKIE` with `verifyDashboardSession`;
    * do not accept `career_sb_token`, any non-empty unknown cookie, or an unverified JWT;
    * make `dashboardAuthErrorResponse` and `dashboardMutationAuthErrorResponse` share this decision function.

    In `dashboard/lib/dashboard-page-auth.ts` and `dashboard/proxy.ts`, call the same validator. The proxy may continue to bypass the login route and route dispatch, but all protected page decisions must use a verified session or verified header.

* [ ] **Step 10: Issue and clear the signed cookie only after valid local-token login.**

    In `dashboard/app/(dashboard)/api/auth/login/route.ts`, accept the existing token form, validate the token with constant-time comparison, and set `career_dashboard_session` with `HttpOnly`, `SameSite=Strict`, `Secure` when production requires it, `Path=/`, and the selected eight-hour/30-day `Max-Age`. Reject the old email/Supabase-cookie branch for dashboard access with a clear `400` response rather than issuing an unvalidated session. In the logout route, expire both the new session cookie and the old `career_sb_token` cookie so stale state cannot confuse operators.

* [ ] **Step 11: Require authenticated same-origin signup and make the server bridge deterministic.**

    In `dashboard/app/(dashboard)/api/auth/signup/route.ts`, require same-origin, then require the shared dashboard auth result, then require `CAREER_ALLOW_LOCAL_SIGNUP=true` before calling FastAPI. In `dashboard/lib/server/fastapi-bridge.ts`, remove Supabase-cookie lookup and throw a configuration error before `fetch()` if `CAREER_DASHBOARD_TOKEN` is missing.

* [ ] **Step 12: Run the complete narrow authentication suites.**

    ```bash
    uv run --group dev python -m pytest -q tests/test_api_auth.py tests/test_api_server.py
    cd /Users/andrejspirov/Career/job-search/dashboard
    NODE_ENV=test npx vitest run lib/server/session.test.ts lib/dashboard-auth.test.ts proxy.test.ts lib/server/fastapi-bridge.test.ts lib/server/architecture.test.ts
    ```

    Expected outcome: all API and dashboard authentication tests pass; no test accepts an arbitrary cookie, `local-dev`, an unverified JWT, or an empty bearer header.

## Task 3: Close the unsafe Supabase persistence path and preserve the SQLite architecture

**Files:**

* Modify: `supabase/migrate_private.py`
* Add: `supabase/README.md`
* Review without executing: `supabase/migrations/20260804_private_job_scan_schema.sql`
* Modify: `docs/ARCHITECTURE.md`
* Modify: `docs/SCHEMAS.md`
* Create: `tests/test_persistence_policy.py`
* Owner decision: quarantine or remove the dormant Supabase files after credential rotation

**Interfaces:**

* `supabase/migrate_private.py` must have no credential literal, no database connection, and a `main()` that exits non-zero with an explicit local-SQLite-only message.
* `docs/ARCHITECTURE.md` and `docs/SCHEMAS.md` remain the source of truth: application persistence is local SQLite under `state/`, with no remote database dependency.
* The SQL migration remains unapplied evidence unless a separately approved Supabase architecture plan is created.

* [ ] **Step 1: Add a regression test that proves the helper is dormant and secret-free.**

    Create `tests/test_persistence_policy.py` with checks that read the helper as text and assert it contains neither a JWT-shaped credential nor `psycopg2.connect`, and that running it returns a non-zero status containing `local SQLite` or `disabled`. Do not import or execute the SQL migration.

* [ ] **Step 2: Run the persistence-policy test before changing the helper.**

    ```bash
    uv run --group dev python -m pytest -q tests/test_persistence_policy.py
    ```

    Expected outcome: failure because the helper currently contains the literal service-role fallback, malformed escaped newlines, and a live connection path.

* [ ] **Step 3: Replace the helper with a fail-closed dormant stub.**

    Reduce `supabase/migrate_private.py` to a documented `main()` that raises `SystemExit` with a message such as `Supabase persistence migration is disabled; application persistence is local SQLite.` Remove all host, user, password, JWT, and database-driver imports. Do not repair or execute the SQL migration as part of this task.

* [ ] **Step 4: Document the dormant directory and the owner-controlled future path.**

    Add `supabase/README.md` stating that the directory is not used by runtime code, the migration is not supported, the helper must not be run, and a future remote-persistence change requires a new reviewed schema, RLS policy, credential design, rollback strategy, and explicit approval. Update `docs/ARCHITECTURE.md` and `docs/SCHEMAS.md` to remove any implication that Supabase is an active fallback for application persistence while retaining the existing SQLite schema contract.

* [ ] **Step 5: Run the persistence and compile checks.**

    ```bash
    uv run --group dev python -m pytest -q tests/test_persistence_policy.py
    uv run python -m compileall -q src cv tests supabase
    ```

    Expected outcome: both commands pass, and no remote connection is attempted.

* [ ] **Step 6: Review the SQL migration without applying it.**

    Record the blockers in the implementation review: invalid `TIMESTAMTZRANGE`/`TIMESTAMPTZRANGE` spellings, nonstandard `pg_md5`, unproven `gen_random_uuid()` dependency, non-reconciling `CREATE TABLE IF NOT EXISTS`, disabled RLS, and divergence from the SQLite schema. Do not add a PostgreSQL driver, run the helper, connect to Supabase, or change the migration into a working remote schema under this plan.

* [ ] **Step 7: Complete the owner approval gate for dormant-file quarantine.**

    After credential rotation, ask the owner whether the two Supabase artifacts and the two malformed configuration artifacts may be moved outside the repository or deleted. If approved, perform that operation as a separate primary-agent action and record the exact paths removed; if not approved, leave the files in place with the fail-closed helper and documentation.

## Task 4: Normalize and strictly validate opportunity configuration

**Files:**

* Modify: `src/career_job_search/opportunities/config_validation.py`
* Modify: `src/career_job_search/opportunities/orchestrator.py`
* Modify: `config/opportunities.example.yaml`
* Modify after owner approval: `config/opportunities.yaml`
* Owner approval required before moving/removing: `config/opportunities.example.yaml.bak`, `config/opportunities.yaml.new`
* Create: `tests/test_opportunity_config.py`
* Modify: `tests/test_sources_helper.py`
* Modify: `tests/test_opportunity_system.py`

**Interfaces:**

* `validate_opportunities_config(raw: Mapping[str, Any]) -> OpportunitiesConfig` validates the complete nested document and raises a `ValueError` containing the source path for every invalid field.
* `canonicalise_opportunities_config(raw: Mapping[str, Any]) -> dict[str, Any]` returns a runtime-shaped dictionary using canonical source keys.
* `load_and_validate_config(path: str | Path | None) -> dict[str, Any]` loads YAML, rejects non-mappings, validates it, and returns canonical runtime data.
* Canonical source keys are `inbox`, `ats`, `company_watchlist`, `linkedin`, `job_board`, `web_search`, `cvmarket_rss`, `cvonline_public_search`, `cvbankas_public_search`, `workinlithuania_public_search`, `uzt_open_data`, and `official_company_careers`.
* Accepted one-release compatibility aliases are `uzt -> uzt_open_data`, `work_in_lithuania -> workinlithuania_public_search`, and `cvmarket_rss.rss_url -> cvmarket_rss.feed_url`. If both an alias and canonical key are present, validation must fail rather than choose silently.
* `job_board.links` and `web_search.links` use a strict `LinkConfig` object with `title`, `url`, optional `company`, optional `location`, and optional `description`; plain strings are invalid.

* [ ] **Step 1: Add failing config-validation tests.**

    Create tests covering:

    ```python
    def test_example_config_is_local_safe():
        config = load_and_validate_config("config/opportunities.example.yaml")
        enabled = {
            name for name, block in config["opportunities"]["sources"].items()
            if block.get("enabled")
        }
        assert enabled == {"inbox"}

    @pytest.mark.parametrize("path", [
        "config/opportunities.yaml",
        "config/opportunities.yaml.new",
    ])
    def test_known_broken_private_artifacts_are_not_accepted(path):
        with pytest.raises((ValueError, FileNotFoundError)):
            load_and_validate_config(path)
    ```

    Add cases for string queries, empty enabled-source queries, string links, unknown nested fields, `uzt`/`uzt_open_data` alias collisions, `rss_url`/`feed_url` collisions, invalid URL paths, and an enabled source with a missing required endpoint.

* [ ] **Step 2: Run the new validation tests and confirm current drift is exposed.**

    ```bash
    uv run --group dev python -m pytest -q tests/test_opportunity_config.py
    ```

    Expected outcome: failures identify the private config’s string links, missing search paths, runtime/validator key mismatch, permissive unknown-field handling, and malformed `.new` artifact.

* [ ] **Step 3: Define complete Pydantic models with conditional enabled-source requirements.**

    Add `ConfigDict(extra="forbid")` to bounded source models and model the `geography`, `scoring`, `liveness`, and `sources` blocks explicitly. Disabled sources may omit network-specific values; enabled sources must satisfy their required fields. Add strict URL and non-empty-text validators, `LinkConfig`, ATS provider validation, and a top-level validator that rejects unknown top-level sections.

* [ ] **Step 4: Implement canonicalization and alias collision errors.**

    Normalize the accepted aliases before runtime dispatch, preserve canonical key names in the returned dictionary, and include the full path in every error. Do not silently discard unknown keys. Keep `suggest_source_fixes()` but make its paths match canonical runtime names.

* [ ] **Step 5: Make the orchestrator consume the single validated loader.**

    Replace the duplicate YAML/validator logic in `orchestrator.load_config()` with `load_and_validate_config()`. Ensure `--config` errors are emitted through the existing JSON envelope and that `path=None` returns an inbox-only local default with an absolute inbox path.

* [ ] **Step 6: Replace the example with a safe opt-in configuration.**

    In `config/opportunities.example.yaml`, retain the scoring and source schemas but set every network, browser, watchlist, ATS, job-board, web-search, UŽT, and LinkedIn source to `enabled: false`; keep only the local inbox enabled. Use canonical field names and object-shaped links. The example must load without making a network request.

* [ ] **Step 7: Repair the private configuration only after explicit owner approval.**

    Convert `config/opportunities.yaml` to canonical names and object-shaped links, correct `cvonline_public_search.base_url` to include `/search`, and remove malformed trace-artifact content. Do not overwrite or delete the existing dirty file without first comparing it with the baseline snapshot. Quarantine or remove `.bak` and `.new` only after the owner approves the operation.

* [ ] **Step 8: Run the configuration and helper suites.**

    ```bash
    uv run --group dev python -m pytest -q tests/test_opportunity_config.py tests/test_sources_helper.py tests/test_opportunity_system.py
    ```

    Expected outcome: the example configuration is accepted and local-safe, malformed private artifacts are rejected or quarantined, aliases normalize deterministically, and helper save/show operations preserve canonical source blocks.

## Task 5: Unify HTTP fetching, retries, and source contracts

**Files:**

* Modify: `src/career_job_search/core/http_client.py`
* Modify: `src/career_job_search/opportunities/sources.py`
* Modify: `src/career_job_search/opportunities/cvmarket_source.py`
* Modify: `src/career_job_search/opportunities/cvonline_source.py`
* Modify: `src/career_job_search/opportunities/cvbankas_source.py`
* Modify: `src/career_job_search/opportunities/workinlithuania_source.py`
* Modify: `src/career_job_search/opportunities/uzt_source.py`
* Modify: `src/career_job_search/opportunities/company_careers_source.py`
* Create: `tests/test_http_client.py`
* Create: `tests/test_opportunity_source_contract.py`
* Modify: `tests/test_opportunity_public_feeds.py`
* Modify: `tests/test_opportunity_company_careers.py`
* Modify: `tests/test_opportunity_source_health.py`
* Modify: `tests/test_opportunity_system.py`
* Modify: `tests/test_architecture.py`

**Interfaces:**

* Preserve the public source wrapper signatures while adding optional source context:

    ```python
    def fetch_text(url: str, *, timeout: int = 20, source_key: str = "default", rate_limit_seconds: float = 0.0) -> str: ...
    def fetch_json(url: str, *, timeout: int = 20, source_key: str = "default", rate_limit_seconds: float = 0.0) -> Any: ...
    def fetch_text_limited(url: str, *, timeout: int = 20, rate_limit_seconds: float = 0.0, source_key: str = "default") -> str: ...
    def fetch_json_limited(url: str, *, timeout: int = 20, rate_limit_seconds: float = 0.0, source_key: str = "default") -> Any: ...
    ```

* `FetchError(url: str, status: int | None, reason: str)` remains the single exhausted-fetch exception.
* Add a thread-safe per-source limiter in `core/http_client.py` keyed by `source_key`, using `time.monotonic()` and a lock. It must not use a mutable default list and must not share one timestamp across unrelated sources.
* `fetch_text_sync()` must use a synchronous `httpx.Client` path or an equivalent safe implementation and must not call `asyncio.run()` from a caller that may already be inside an event loop.
* Retry statuses are `429`, `502`, `503`, and `504`; retryable network errors include timeout, connection, and remote-protocol failures. Non-retryable statuses return/raise immediately according to the existing wrapper contract.

* [ ] **Step 1: Add failing HTTP-client tests.**

    Create tests for retrying a `503` then returning `200`, exhausting retries into `FetchError`, forwarding headers and timeout, isolating rate-limit state by source key, serializing concurrent same-source calls, and calling the synchronous wrapper from an active async test without a nested-event-loop error.

* [ ] **Step 2: Run the HTTP tests before implementation.**

    ```bash
    uv run --group dev python -m pytest -q tests/test_http_client.py
    ```

    Expected outcome: failures expose the missing thread-safe limiter and the current `asyncio.run()` behavior.

* [ ] **Step 3: Implement the shared HTTP contract.**

    Remove unused `time`/`Any` imports, create one retry loop per async/sync transport, close clients in `finally`/context-manager blocks, retain response text for diagnostics, and redact authorization-like values from error messages. Keep delays injectable in tests so no test sleeps for real seconds.

* [ ] **Step 4: Add failing source-contract tests for configuration and wrapper behavior.**

    Test that `_rate_limited_fetcher()` forwards caller `timeout` and other supported keyword arguments, binds the configured canonical source key, uses independent rate limits for `cvmarket_rss` and `uzt_open_data`, and reports a failed `SourceResult` instead of raising through the whole batch. Test that enabled external sources use mocked fetchers and disabled sources make zero fetch calls.

* [ ] **Step 5: Run the source-contract tests against the current source registry.**

    ```bash
    uv run --group dev python -m pytest -q tests/test_opportunity_source_contract.py tests/test_opportunity_source_health.py
    ```

    Expected outcome: failures identify ignored wrapper kwargs, shared mutable rate-limit state, legacy urllib exception handling, and canonical-key drift.

* [ ] **Step 6: Remove the duplicate urllib retry implementation from `sources.py`.**

    Delete the `Request`, `urlopen`, `HTTPError`, `URLError`, `sleep`, and legacy `_retry_with_backoff()` path after replacing its callers with the shared client. Fix import ordering and add the missing callable type import only where the final implementation needs it. Keep `fetch_json()` and `fetch_text()` as compatibility wrappers that delegate to `core.http_client`.

* [ ] **Step 7: Bind every source to the canonical fetch and config interfaces.**

    Update source-specific adapters to consume `feed_url`, `base_url`, and canonical source blocks. Change UŽT dispatch to `uzt_open_data` and Work in Lithuania dispatch to `workinlithuania_public_search`. Ensure wrapper lambdas pass caller kwargs rather than discarding them. Keep ATS provider caps and source result metadata unchanged.

* [ ] **Step 8: Keep `sources.py` within the architecture size limit.**

    Run the architecture line-count test. The removal of duplicate fetch/retry code must bring `sources.py` below the existing 850-line production-module bound. If it remains over the bound, move only the source-result collection helpers into a new focused `src/career_job_search/opportunities/source_collection.py` and update imports; do not create a generic “utils” dumping ground.

* [ ] **Step 9: Run all source and HTTP tests.**

    ```bash
    uv run --group dev python -m pytest -q tests/test_http_client.py tests/test_opportunity_source_contract.py tests/test_opportunity_public_feeds.py tests/test_opportunity_company_careers.py tests/test_opportunity_source_health.py tests/test_opportunity_system.py tests/test_architecture.py
    ```

    Expected outcome: deterministic mocked-source tests pass, no external request is made by the example config, source names agree across validation and dispatch, and the architecture bound passes.

## Task 6: Centralize salary semantics and make `--since` strict

**Files:**

* Create: `src/career_job_search/opportunities/salary.py`
* Modify: `src/career_job_search/opportunities/matching.py`
* Modify: `src/career_job_search/opportunities/preferences.py`
* Modify: `src/career_job_search/opportunities/orchestrator.py`
* Modify: `tests/test_opportunities_matching.py`
* Create: `tests/test_opportunity_salary.py`
* Create: `tests/test_opportunity_since.py`
* Modify: `tests/test_opportunity_system.py`

**Interfaces:**

* `salary.py` exports:

    ```python
    class SalaryRange(NamedTuple):
        minimum: float
        maximum: float
        currency: str
        period: Literal["monthly", "annual", "hourly", "unknown"]

    def parse_salary_range(text: str) -> SalaryRange | None: ...
    def monthly_salary_range_eur(text: str) -> tuple[float, float] | None: ...
    ```

* `matching.salary_score(opportunity)` uses `monthly_salary_range_eur()` and retains a maximum score contribution of `2.5` (`1.0 + min(monthly_max / 5000, 1.5)`). A missing or unparseable salary contributes `0.0`.
* `preferences._salary_monthly_eur()` becomes a thin call to `monthly_salary_range_eur()` and returns the lower monthly bound rounded to an integer.
* Add `parse_since_argument(value: str) -> datetime` and `should_match_since(row: Opportunity, since: datetime) -> bool` in `orchestrator.py` or a focused helper. Both must use UTC-aware datetimes.

* [ ] **Step 1: Add failing salary parser tests.**

    Create parametrized cases asserting these normalized results:

    ```python
    assert monthly_salary_range_eur("30k EUR/year") == (2500.0, 2500.0)
    assert monthly_salary_range_eur("2.5k EUR/month") == (2500.0, 2500.0)
    assert monthly_salary_range_eur("2.5m EUR/year") == (208333.33333333334, 208333.33333333334)
    assert monthly_salary_range_eur("3,400-4,500 EUR/month") == (3400.0, 4500.0)
    assert monthly_salary_range_eur("2.630 EUR/month") == (2630.0, 2630.0)
    ```

    Include annual aliases (`annual`, `annum`, `per year`, `/yr`), monthly aliases, `k`/`m` with comma and dot decimals, European thousands, ranges, missing currency, and numeric artifacts below €100.

* [ ] **Step 2: Run the salary tests before implementation.**

    ```bash
    uv run --group dev python -m pytest -q tests/test_opportunity_salary.py tests/test_opportunities_matching.py
    ```

    Expected outcome: the current parser fails annual normalization and `m` notation, while existing monthly/range tests show the legacy behavior that must be preserved deliberately.

* [ ] **Step 3: Implement one parser and delegate both consumers to it.**

    Parse numeric tokens with their nearest suffix and period context, distinguish European thousands from decimals, expand `k` by 1,000 and `m` by 1,000,000, preserve range endpoints, and normalize annual values to monthly by dividing by 12. Treat an otherwise unitless numeric salary as monthly for scoring compatibility, but require EUR/€ for the preferences minimum-salary comparison.

* [ ] **Step 4: Run the salary and matching suites.**

    ```bash
    uv run --group dev python -m pytest -q tests/test_opportunity_salary.py tests/test_opportunities_matching.py
    ```

    Expected outcome: all new normalization cases and existing score/risk tests pass with updated expectations where annual semantics intentionally changed.

* [ ] **Step 5: Add failing strict-`--since` tests.**

    Create `tests/test_opportunity_since.py` with rows covering:

    * an old row with no match;
    * an old row with low score and `NEW` status;
    * a row whose `last_seen_at` is after the cutoff;
    * a row whose `live_checked_at` is after the cutoff;
    * empty timestamps;
    * naive timestamps;
    * invalid timestamps;
    * `Z`, UTC-offset, and Europe/Vilnius-offset timestamps representing the same instant.

    Assert that only rows with a parsed timestamp at or after the cutoff are selected. Assert that an invalid or naive timestamp raises a clear `ValueError` rather than being silently included.

* [ ] **Step 6: Run the strict-`--since` tests against the current implementation.**

    ```bash
    uv run --group dev python -m pytest -q tests/test_opportunity_since.py tests/test_opportunity_system.py
    ```

    Expected outcome: failures expose the current `startswith()`, string-comparison, status, score, and `match is None` shortcuts.

* [ ] **Step 7: Implement parsed, timezone-aware cutoff selection.**

    Parse a date-only CLI value as midnight UTC and accept a full ISO-8601 value only when it includes timezone information. Parse every candidate timestamp with `datetime.fromisoformat()`, convert it to UTC, and compare the instant. With `--since`, include a row only when at least one defined freshness timestamp (`first_seen_at`, `last_seen_at`, `first_eligible_at`, or `live_checked_at`) is at or after the cutoff. Empty timestamps do not qualify. Invalid or naive timestamps fail the command with a JSON error and exit code `1`.

* [ ] **Step 8: Run matching, preference, and orchestration tests.**

    ```bash
    uv run --group dev python -m pytest -q tests/test_opportunity_salary.py tests/test_opportunities_matching.py tests/test_opportunity_since.py tests/test_opportunity_system.py
    ```

    Expected outcome: salary semantics are shared, stale rows are excluded regardless of status/score, timestamp errors are visible, and existing daily queue behavior remains intact.

## Task 7: Make dashboard tests and toolchain behavior explicit

**Files:**

* Modify: `dashboard/vitest.config.ts`
* Modify: `dashboard/package.json` only after dependency approval
* Modify: `dashboard/package-lock.json` only after dependency approval
* Modify: `dashboard/eslint.config.mjs` if required by the approved ESLint package versions
* Modify: `dashboard/app/(dashboard)/notifications/__tests__/notification-inbox.test.tsx`
* Modify: `dashboard/lib/__tests__/setup.ts` only if the explicit environment split requires it
* Modify: `dashboard/lib/dashboard-auth.test.ts`
* Modify: `dashboard/proxy.test.ts`
* Modify: `Makefile`
* Create or modify: `dashboard/app/(dashboard)/api/auth/signup/route.test.ts`

**Interfaces:**

* Vitest’s default environment is `node` for server and utility tests. The notification React test explicitly opts into jsdom using a file-level Vitest environment directive.
* The package test command sets `NODE_ENV=test` so inherited shell production settings cannot change the test runtime.
* `make dashboard-test` runs the same explicit test mode followed by typecheck; it does not rely on an unset environment variable.
* Lint is a separate gate and may not be claimed as passing while ESLint is absent from the lockfile.

* [ ] **Step 1: Add a regression test that proves the test command is environment-independent.**

    Add a small test or command-level check that runs the server-auth suite under `NODE_ENV=production` and `NODE_ENV=test`, asserting the same result. Keep the React notification test in jsdom and server tests in Node.

* [ ] **Step 2: Change Vitest configuration to an explicit Node default.**

    In `dashboard/vitest.config.ts`, import path helpers from `node:path`/`node:url`, set `environment: 'node'`, and use `environmentMatchGlobs` or a file-level directive for `*.test.tsx` to select jsdom. Add the jsdom directive to `notification-inbox.test.tsx`. Do not make server authentication tests depend on a browser-like global environment.

* [ ] **Step 3: Make the package and Makefile test commands explicit.**

    Change the dashboard `test` script to run Vitest with `NODE_ENV=test`, and change `make dashboard-test` to invoke `NODE_ENV=test npm test && npm run typecheck`. Preserve the existing build and E2E commands.

* [ ] **Step 4: Run dashboard tests under both relevant environments.**

    ```bash
    cd /Users/andrejspirov/Career/job-search/dashboard
    NODE_ENV=production npm test
    NODE_ENV=test npm test
    npm run typecheck
    npm run build
    ```

    Expected outcome: both test invocations pass with identical test counts, typecheck passes, and build passes. No `resolve is not a function` or `React.act is not a function` error remains.

* [ ] **Step 5: Resolve the ESLint dependency gap only after approval.**

    Owner approval is required before editing package metadata or the lockfile. After approval, add compatible exact top-level development dependencies for the existing flat ESLint configuration, run `npm install`, and verify that the generated `dashboard/package-lock.json` contains both ESLint and the Next.js config package. Do not bypass lint by deleting the script or suppressing all rules.

* [ ] **Step 6: Run the approved lint gate and record any real source findings.**

    ```bash
    cd /Users/andrejspirov/Career/job-search/dashboard
    npm run lint
    ```

    Expected outcome: ESLint is found. Any remaining lint findings are fixed in the relevant source files and rechecked; a missing executable is no longer the reported failure.

## Task 8: Repair release verification, CI naming, and operational documentation

**Files:**

* Modify: `scripts/verify_release.sh`
* Modify: `Makefile`
* Modify: `.github/workflows/ci.yml`
* Modify: `docs/REQUIRED_CHECKS.md`
* Modify: `docs/OPERATIONS_RUNBOOK.md`
* Modify: `README.md`
* Modify: `.github/workflows/ci.yml` only for workflow definitions; do not change GitHub branch-protection settings
* Create: `tests/test_release_script.py` if shell behavior needs a repository-level regression test

**Interfaces:**

* `scripts/verify_release.sh` must use a temporary directory created with `mktemp -d "${TMPDIR:-/tmp}/job-search-runtime.XXXXXX"`, write `requirements.txt` inside it, and remove the directory in `cleanup()`.
* The release script must install/check the same canonical Python paths used by `AGENTS.md`: `src cv tests`, not stale `tools`/`mcp` paths.
* CI display names and `docs/REQUIRED_CHECKS.md` must describe the same gates. Do not alter repository settings, rulesets, branch protection, or required-check configuration through code.
* Operational docs must describe the token/session environment variables, local SQLite persistence, disabled-by-default external sources, and the safe commands for dashboard tests and release verification.

* [ ] **Step 1: Add a regression test or shell harness for the macOS temporary-file failure.**

    Test the temporary-directory fragment independently with a temporary `TMPDIR` and assert that it creates a unique directory, writes a requirements file, and removes it on exit. The test must not run the full release gate or touch `runtime/release-check.lock`.

* [ ] **Step 2: Fix temporary-directory lifecycle and lock cleanup.**

    In `scripts/verify_release.sh`, create the temporary directory before the lock attempt, install a cleanup trap immediately, track whether the lock was created, and remove only the lock directory created by this invocation. Preserve the existing behavior of refusing a concurrent release check. Replace the non-portable `/tmp/...XXXXXX.txt` call with the directory pattern above.

* [ ] **Step 3: Align local Make targets with the canonical paths and environment.**

    Replace stale `src mcp tools cv tests` lint/format/doctor paths with `src cv tests` where the current policy requires them. Make `dashboard-test` use `NODE_ENV=test`. Make `audit-runtime` use a temporary directory with cleanup rather than a fixed `/tmp/job-search-runtime-requirements.txt`. Do not change recruiter live-dispatch safety ceilings.

* [ ] **Step 4: Align CI job names and commands with the documented release gates.**

    Update `.github/workflows/ci.yml` so the displayed jobs cover lock check, Python lint/tests/PDFs/audit, dashboard unit/typecheck/build/browser/audit, repository smoke, and both CodeQL languages. Use `uv run ruff check src cv tests`, the explicit dashboard test environment, and temporary requirement directories. Keep the workflow’s existing private-repository assumptions and do not edit GitHub settings.

* [ ] **Step 5: Update required-check documentation to match actual workflow names.**

    Replace stale job identifiers in `docs/REQUIRED_CHECKS.md` with the exact CI display names produced by the workflow. Keep the statement that enabling branch protection or rulesets is an external owner action and must not be performed by the agent.

* [ ] **Step 6: Remove stale operational references.**

    Search the named documentation and command files:

    ```bash
    rg -n '\btools\b|mcp|career_sb_token|SUPABASE_SERVICE_ROLE_KEY|mktemp /tmp|NODE_ENV' Makefile scripts/verify_release.sh .github/workflows/ci.yml docs/OPERATIONS_RUNBOOK.md README.md docs/REQUIRED_CHECKS.md
    ```

    Replace each stale command or authentication description with the canonical package commands, signed-session variables, local SQLite statement, or explicit owner action. Do not expose credentials in documentation.

* [ ] **Step 7: Run the release-script and documentation checks.**

    ```bash
    bash -n scripts/verify_release.sh
    make dashboard-test
    make verify-release
    ```

    Expected outcome: shell syntax passes, dashboard tests and typecheck pass in explicit test mode, and the release gate proceeds beyond the former macOS `mktemp` error. If a later gate fails, retain its real diagnostic and do not mask it with `|| true`.

## Task 9: Final integrated verification and review gates

**Files:**

* Inspect: `/Users/andrejspirov/Career/job-search-baseline-20260806.status`
* Inspect: `/Users/andrejspirov/Career/job-search-baseline-20260806.patch`
* Verify all files listed in Tasks 2–8
* Update: `.memory/topics/main-codex-noise-remediation-2026-08-04.md` only through the repository’s approved memory command and only after implementation is verified

**Interfaces:**

* Produces verified command output for every release gate.
* Produces a final dirty-worktree comparison that separates planned edits from the pre-existing baseline.
* Produces a concise handoff listing remaining owner actions and any intentionally deferred Supabase/dependency work.

* [ ] **Step 1: Run static and unit verification in the canonical order.**

    ```bash
    cd /Users/andrejspirov/Career/job-search
    git diff --check
    uv run python -m compileall -q src cv tests supabase
    uv run ruff check src cv tests
    uv run --group dev python -m pytest -q
    (cd dashboard && NODE_ENV=test npm test)
    (cd dashboard && npm run typecheck)
    (cd dashboard && npm run build)
    (cd dashboard && npm run lint)
    ```

    Expected outcome: every command exits zero. If a command fails, fix or document the concrete failure before claiming completion; do not substitute a weaker command.

* [ ] **Step 2: Run the complete release gate and smoke test.**

    ```bash
    make verify-release
    ./scripts/smoke_repo.sh
    ```

    Expected outcome: the release script completes all Python, CV, dashboard, browser, audit, and smoke stages without the temporary-file failure and without deleting a pre-existing release lock.

* [ ] **Step 3: Run a non-disclosing security regression scan.**

    ```bash
    rg -l 'LEGACY_TOKEN|local-dev|career_sb_token|Authorization: Bearer \$|SUPABASE_SERVICE_ROLE_KEY' src dashboard supabase docs README.md || true
    rg -l 'eyJhbGciOiJIUzI1Ni' src dashboard supabase config docs README.md || true
    ```

    Expected outcome: no production authentication path, documentation file, or retained helper contains the legacy fallback, the old cookie name as an authorization signal, an empty-bearer construction, or a JWT literal. The command prints file names only; never print matching secret contents.

* [ ] **Step 4: Compare the final worktree against the captured baseline.**

    ```bash
    git status --short
    git diff --stat
    git diff --check
    diff -u ../job-search-baseline-20260806.status <(git status --short) || true
    ```

    Expected outcome: every additional changed path is explained by Tasks 2–8 or an owner-approved operation. Unrelated dirty changes remain intact; no generated state, ignored credentials, lock directories, or historical files are removed.

* [ ] **Step 5: Perform the plan self-review before reporting completion.**

    * **Requirements coverage:** confirm that credential rotation, legacy token removal, signed-cookie verification, bridge fail-closed behavior, signup policy, SQLite/Supabase decision, config drift, source retries/rate limits, strict `--since`, salary normalization, Vitest environment, ESLint dependency gap, `mktemp`, stale `tools` references, CI, and documentation each have a completed task and passing check.
    * **Placeholder scan:** run `rg -n 'T[B]D|T[O]DO|implement later|fill in details' docs/superpowers/plans/2026-08-04-career-job-search-hardening.md` and resolve every match that is not part of the scan command itself.
    * **Type/signature consistency:** verify that every caller uses the exact session, bridge, config-loader, salary, and fetch signatures defined in the task interfaces; run Python type-sensitive tests, `npm run typecheck`, and the complete test suites again after any correction.
    * **Security review:** confirm that no cookie-presence check remains, no API fallback remains, no secret is present in tracked source or documentation, and no remote migration was executed.
    * **Operational review:** confirm that the owner has completed credential rotation and has explicitly approved any quarantine, dependency, deletion, migration, or GitHub-settings action still listed as pending.

* [ ] **Step 6: Record a one-line handoff only after all verification succeeds.**

    ```bash
    make remember TOPIC=main-codex-noise-remediation-2026-08-04 MSG="Completed the approved career job-search hardening plan; verification gates passed; remaining owner actions: <list only concrete pending actions>."
    ```

    Expected outcome: the memory update contains no credentials, ignored state, or unverified success claim.

## Execution strategy

* Tasks 1–3 remain with the primary agent because they involve credentials, authentication, persistence, and policy decisions.
* Tasks 4–6 can be dispatched independently only after Task 1 decisions are approved and the baseline snapshot is captured; each must return its test output and changed-file list for review.
* Task 7 remains primary-agent work when it changes dependencies or lockfiles; the environment-only Vitest changes may be dispatched separately.
* Task 8 remains primary-agent work because it changes release gates and operational policy.
* Task 9 is always performed by the primary agent after reviewing every delegated change. No subagent may receive ignored state, secrets, or the baseline patch.

## Self-review result

* **Spec coverage:** Tasks 1–9 cover all security, persistence, configuration, source, matching, dashboard, release, CI, documentation, and verification findings identified in the repository review.
* **Placeholder scan:** The plan uses concrete paths, signatures, commands, expected outcomes, owner gates, and test names; it does not defer implementation to an unspecified future step.
* **Type consistency:** The signed-session claims, bridge header function, canonical config loader, shared salary range, fetch wrappers, and strict cutoff selector are defined once and referenced consistently by later tasks.
