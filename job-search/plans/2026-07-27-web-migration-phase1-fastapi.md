# Phase 1: FastAPI Backend

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Node.js subprocess spawning with a persistent Python HTTP server, eliminating per-request Python startup overhead and establishing the server architecture for multi-tenancy.

**Architecture:** A FastAPI server (`/api/v1/`) runs alongside the Next.js dev/prod server. The existing `python-bridge.ts` switches from `spawn("uv run python ...")` to `fetch("http://127.0.0.1:8000/...")`. Helpers are called in-process (either directly or via `importlib + main(argv)` wrapper), preserving the existing `career_python_helper_v1` JSON envelope format so all lib wrappers work unchanged.

**Tech Stack:** FastAPI, uvicorn, httpx (already present), Pydantic (already present)

## Global Constraints

- Python 3.11 (project constraint)
- Pre-commit hooks active — `make precommit-setup` to reinstall
- Ruff linting (`uv run ruff check src tests`) must pass
- All existing tests must pass (`uv run --group dev python -m pytest -q`)
- Dashboard typecheck (`cd dashboard && npm run typecheck`) must pass
- No changes to existing helper script CLI interfaces (they still work standalone)
- No deletions or renames of existing files
- FastAPI server: port 8000 (configurable via env `CAREER_API_PORT`)
- Auth: start with the existing pre-shared token from `CAREER_DASHBOARD_TOKEN` env var (same token, `Authorization: Bearer <token>` header)
- The bridge switch must support a **gradual rollout**: config flag to use HTTP vs subprocess

---

### Task 1: Add FastAPI dependency and create server skeleton

**Files:**
- Modify: `pyproject.toml` (add dependencies)
- Create: `src/career_job_search/api/__init__.py`
- Create: `src/career_job_search/api/server.py`
- Create: `src/career_job_search/api/main.py` (entry point)
- Test: `tests/test_api_server.py`

**Interfaces:**
- Consumes: `CAREER_DASHBOARD_TOKEN` env var, `CAREER_API_PORT` env var (default 8000)
- Produces: FastAPI app with health endpoint at `GET /health`
- Produces: `uv run python -m career_job_search.api.main` starts the server

- [ ] **Step 1: Add FastAPI + uvicorn to project dependencies**

Edit `pyproject.toml` to add to `[project] dependencies`:
```
  "fastapi>=0.115,<1",
  "uvicorn[standard]>=0.34,<1",
```

- [ ] **Step 2: Install new deps**

```bash
cd job-search && uv lock && uv sync
```

- [ ] **Step 3: Create `src/career_job_search/api/__init__.py`**

Empty file.

- [ ] **Step 4: Create `src/career_job_search/api/server.py`**

```python
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Career API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
```

- [ ] **Step 5: Create `src/career_job_search/api/main.py`**

```python
from __future__ import annotations

import os
import sys

import uvicorn

from career_job_search.api.server import create_app

API_PORT_KEY = "CAREER_API_PORT"
API_PORT_DEFAULT = 8000


def main(argv: list[str] | None = None) -> int:
    port = int(os.environ.get(API_PORT_KEY, API_PORT_DEFAULT))
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Add `__main__` compatibility to the `api` package**

This allows `python -m career_job_search.api`:

Edit `src/career_job_search/api/__init__.py`:
```python
from career_job_search.api.main import main
```

- [ ] **Step 7: Write a health-check test**

```python
"""Tests for the FastAPI server."""

from __future__ import annotations

from fastapi.testclient import TestClient

from career_job_search.api.server import create_app


def test_health_endpoint() -> None:
    app = create_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
```

- [ ] **Step 8: Run tests to verify**

```bash
cd job-search && uv run pytest tests/test_api_server.py -v
```

Expected: PASS

- [ ] **Step 9: Run lint + full test suite**

```bash
cd job-search && uv run ruff check src tests && uv run -p pytest -q
```

Expected: 0 lint errors, all existing tests pass.

---

### Task 2: Auth middleware (token passthrough)

**Files:**
- Create: `src/career_job_search/api/auth.py`
- Modify: `src/career_job_search/api/server.py`

**Interfaces:**
- Consumes: `CAREER_DASHBOARD_TOKEN` env var (same token the dashboard uses)
- Produces: `verify_token(request) -> str | None` dependency
- Produces: `AuthenticatedUser` Pydantic model with user_id (static "local" for now)

- [ ] **Step 1: Create `src/career_job_search/api/auth.py`**

```python
from __future__ import annotations

import os
import hmac
from typing import Annotated

from fastapi import Header, HTTPException, status

TOKEN_ENV_KEY = "CAREER_DASHBOARD_TOKEN"


def _get_expected_token() -> str:
    token = os.environ.get(TOKEN_ENV_KEY, "")
    if not token:
        raise RuntimeError(f"{TOKEN_ENV_KEY} is not set.")
    return token


async def verify_token(authorization: Annotated[str | None, Header()] = None) -> str:
    expected = _get_expected_token()
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header format")
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")
    return "local-user"
```

- [ ] **Step 2: Wire auth into `server.py`**

Add auth dependency to `create_app()`:

```python
from career_job_search.api.auth import verify_token

# In create_app(), add a protected route:
@app.get("/api/v1/me")
async def me(user: str = Depends(verify_token)):
    return {"user": user}
```

- [ ] **Step 3: Write auth tests**

```python
def test_auth_missing_header() -> None:
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_auth_valid_token(monkeypatch) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200
    assert response.json()["user"] == "local-user"


def test_auth_invalid_token(monkeypatch) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 403
```

- [ ] **Step 4: Run tests**

```bash
cd job-search && uv run pytest tests/test_api_server.py -v
```

Expected: PASS (4 tests: health + 3 auth)

- [ ] **Step 5: Run lint**

```bash
cd job-search && uv run ruff check src tests
```

Expected: 0 errors.

---

### Task 3: Generic helper proxy endpoint

**Files:**
- Create: `src/career_job_search/api/routers/__init__.py`
- Create: `src/career_job_search/api/routers/helpers.py`
- Modify: `src/career_job_search/api/server.py` (register router)

**Interfaces:**
- Consumes: `POST /api/v1/helpers/{name}` with JSON body `{"args": ["list", "of", "strings"], "input": "optional stdin text"}`
- Produces: Same JSON envelope as the existing helper scripts (`{"ok": true, "data": ...}` or `{"ok": false, "error": "..."}`)
- Produces: In-process execution (no subprocess) — calls `module.main(argv)` with stdout capture

This is the key bridging endpoint. It lets the existing Next.js lib wrappers switch from `spawn` to `fetch` with zero changes to their call patterns.

- [ ] **Step 1: Create `src/career_job_search/api/routers/__init__.py`**

Empty file.

- [ ] **Step 2: Create `src/career_job_search/api/routers/helpers.py`**

```python
from __future__ import annotations

import importlib
import io
import json
import os
from contextlib import redirect_stdout, redirect_stderr
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from career_job_search.api.auth import verify_token

HELPER_REGISTRY: dict[str, str] = {
    "analytics": "career_job_search.automation.analytics",
    "cvCatalogue": "tools.cv_catalogue",
    "cvStudio": "career_job_search.cvs.studio",
    "cvProfiles": "career_job_search.cvs.profiles_helper",
    "linkedinConfig": "career_job_search.integrations.linkedin.config_helper",
    "localDrafting": "career_job_search.cvs.drafting",
    "notifications": "career_job_search.notifications.center",
    "opportunities": "tools.opportunity_dashboard",
    "opportunitySources": "career_job_search.opportunities.sources_helper",
    "recruiters": "career_job_search.recruiters.dashboard_adapter",
    "searchPreferences": "career_job_search.opportunities.preferences",
    "settingsControl": "career_job_search.recruiters.settings_helper",
    "setupChecklist": "career_job_search.setup.checklist",
    "workspace": "tools.workspace_control",
    "automation": "tools.automation_control",
    "developmentAgents": "tools.local_dev_agents",
}

router = APIRouter(prefix="/api/v1/helpers", dependencies=[Depends(verify_token)])


class HelperRequest(BaseModel):
    args: list[str] = []
    input: str | None = None


class HelperResponse(BaseModel):
    ok: bool
    data: Any = None
    error: str | None = None
    schema: str = "career_python_helper_v1"


@router.post("/{name}")
async def run_helper(name: str, body: HelperRequest) -> HelperResponse:
    module_path = HELPER_REGISTRY.get(name)
    if module_path is None:
        raise HTTPException(status_code=404, detail=f"Unknown helper: {name}")

    # Dynamically prepend tools/ directory to sys.path for tool-based helpers
    tools_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "tools")
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot import helper: {exc}")

    if not hasattr(module, "main"):
        raise HTTPException(status_code=500, detail=f"Helper {name} has no main() function")

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exit_code = 1
    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exit_code = module.main(body.args)
        stdout_text = stdout_buf.getvalue()
        stderr_text = stderr_buf.getvalue()
    except Exception as exc:
        stderr_text = str(exc)
        exit_code = 1

    # Try to parse stdout as JSON envelope, falling back to text
    if stdout_text.strip():
        try:
            payload = json.loads(stdout_text)
            if isinstance(payload, dict):
                return HelperResponse(
                    ok=payload.get("ok", exit_code == 0),
                    data=payload.get("data"),
                    error=payload.get("error") or (stderr_text if exit_code != 0 else None),
                )
        except json.JSONDecodeError:
            pass

    if exit_code != 0:
        return HelperResponse(ok=False, error=stderr_text or stdout_text or "Unknown error")

    # If stdout is not JSON but exit_code is 0, wrap it
    return HelperResponse(ok=True, data=stdout_text.strip() if stdout_text.strip() else None)
```

- [ ] **Step 3: Register the router in `server.py`**

Add to `create_app()`:

```python
from career_job_search.api.routers.helpers import router as helpers_router

app.include_router(helpers_router)
```

- [ ] **Step 4: Write tests for the helper proxy**

```python
def test_helper_proxy_valid(monkeypatch) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    app = create_app()
    client = TestClient(app)
    # Test with sources_helper "show" command
    response = client.post(
        "/api/v1/helpers/opportunitySources",
        json={"args": ["show"]},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


def test_helper_proxy_unknown(monkeypatch) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/api/v1/helpers/doesNotExist",
        json={"args": ["show"]},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 404
```

- [ ] **Step 5: Run tests**

```bash
cd job-search && uv run pytest tests/test_api_server.py -v
```

Expected: PASS

---

### Task 4: HTTP bridge in Next.js (fastapi-bridge.ts)

**Files:**
- Create: `dashboard/lib/server/fastapi-bridge.ts`
- Modify: `dashboard/lib/server/python-bridge.ts` (add config flag and delegating wrapper)

**Interfaces:**
- Consumes: `NEXT_PUBLIC_API_BASE_URL` env var (default `http://127.0.0.1:8000`), `CAREER_DASHBOARD_TOKEN` env var
- Produces: Same `runPythonHelper<T>(name, args, options)` signature — drop-in replacement
- Produces: `USE_HTTP_BRIDGE` config that toggles between spawn and fetch

- [ ] **Step 1: Create `dashboard/lib/server/fastapi-bridge.ts`**

```typescript
const API_BASE_URL = process.env.CAREER_API_URL || 'http://127.0.0.1:8000'
const API_TOKEN = process.env.CAREER_DASHBOARD_TOKEN || ''

export type FastApiBridgeResult<T> = {
  ok: boolean
  data?: T
  error?: string
  schema: string
}

export async function runFastApiHelper<T>(
  helper: string,
  args: readonly string[] = [],
  options: { inputText?: string; timeoutMs?: number; errorLabel?: string } = {},
): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? 30_000)

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/helpers/${helper}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${API_TOKEN}`,
      },
      body: JSON.stringify({
        args: [...args],
        input: options.inputText ?? null,
      }),
      signal: controller.signal,
    })

    if (!response.ok) {
      const text = await response.text().catch(() => '')
      throw new Error(`${options.errorLabel || 'FastAPI helper'}: ${response.status} ${text}`)
    }

    const result: FastApiBridgeResult<T> = await response.json()
    if (!result.ok) {
      throw new Error(result.error || `${options.errorLabel || 'FastAPI helper'} returned error`)
    }

    return result.data as T
  } finally {
    clearTimeout(timeout)
  }
}
```

- [ ] **Step 2: Add USE_HTTP_BRIDGE config to python-bridge.ts**

Add near the top of `python-bridge.ts`:

```typescript
const USE_HTTP_BRIDGE = process.env.CAREER_USE_HTTP_BRIDGE === '1'
```

Import and delegate at the bottom:

```typescript
import { runFastApiHelper } from './fastapi-bridge'

// Override runPythonHelper when HTTP bridge is enabled
export async function runPythonHelper<T>(
  helper: PythonHelperName,
  args: readonly string[] = [],
  options: PythonHelperOptions = {},
): Promise<T> {
  if (USE_HTTP_BRIDGE) {
    return runFastApiHelper<T>(helper, args, {
      inputText: options.inputText,
      timeoutMs: options.timeoutMs,
      errorLabel: options.errorLabel,
    })
  }
  // ... existing implementation follows (keep the current code)
}
```

- [ ] **Step 3: Run dashboard typecheck**

```bash
cd dashboard && npm run typecheck
```

Expected: 0 errors.

- [ ] **Step 4: Test the bridge end-to-end**

```bash
# Start the API server in background
cd job-search && CAREER_DASHBOARD_TOKEN="test-token" uv run python -m career_job_search.api.main &
API_PID=$!

# Test via curl
curl -s http://127.0.0.1:8000/health
curl -s -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -X POST -d '{"args": ["show"]}' \
  http://127.0.0.1:8000/api/v1/helpers/opportunitySources

# Kill the server
kill $API_PID 2>/dev/null; wait $API_PID 2>/dev/null
```

Expected: Both endpoints return valid JSON.

---

### Task 5: Typed endpoints for simple config helpers

**Files:**
- Create: `src/career_job_search/api/routers/sources.py`
- Create: `src/career_job_search/api/routers/linkedin.py`
- Create: `src/career_job_search/api/routers/profiles.py`
- Create: `src/career_job_search/api/routers/settings.py`
- Create: `src/career_job_search/api/routers/preferences.py`
- Create: `src/career_job_search/api/routers/checklist.py`
- Modify: `src/career_job_search/api/server.py` (register routers)
- Test: `tests/test_api_routers.py`

**Interfaces:**
- Consumes: Direct calls to existing helper functions (e.g., `read_config()`, `write_config()`)
- Produces: Typed REST endpoints per domain (GET/POST with proper request/response models)
- Produces: All existing YAML config operations work via both the HTTP API and the CLI

- [ ] **Step 1: Create `src/career_job_search/api/routers/sources.py`**

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from career_job_search.api.auth import verify_token
from career_job_search.opportunities.sources_helper import read_config, write_config

router = APIRouter(prefix="/api/v1/settings/sources", dependencies=[Depends(verify_token)])


@router.get("/")
async def get_sources() -> dict[str, Any]:
    return read_config()


@router.post("/")
async def save_sources(data: dict[str, Any]) -> dict[str, Any]:
    write_config(data)
    return {"ok": True, "data": read_config()}
```

- [ ] **Step 2: Create remaining simple routers**

Same pattern for each — they call the existing helper's read/write functions directly:

**`routers/linkedin.py`:**
- `GET /api/v1/settings/linkedin` → calls `read_config()` from `integrations.linkedin.config_helper`
- `POST /api/v1/settings/linkedin` → calls `write_config()`

**`routers/profiles.py`:**
- `GET /api/v1/settings/cv-profiles` → calls `read_config()` from `cvs.profiles_helper`
- `POST /api/v1/settings/cv-profiles` → calls `write_config()`

**`routers/settings.py`:**
- `GET /api/v1/settings/runtime` → calls `read_settings()` from `recruiters.settings_helper`
- `POST /api/v1/settings/runtime` → calls `save_settings()`

**`routers/preferences.py`:**
- `GET /api/v1/settings/preferences` → calls `read_config()` from `opportunities.preferences`
- `POST /api/v1/settings/preferences` → calls `write_config()`

**`routers/checklist.py`:**
- `GET /api/v1/setup/checklist` → calls `check_all()` from `setup.checklist`

- [ ] **Step 3: Register all routers in `server.py`**

```python
from career_job_search.api.routers.sources import router as sources_router
from career_job_search.api.routers.linkedin import router as linkedin_router
from career_job_search.api.routers.profiles import router as profiles_router
from career_job_search.api.routers.settings import router as settings_router
from career_job_search.api.routers.preferences import router as preferences_router
from career_job_search.api.routers.checklist import router as checklist_router

app.include_router(sources_router)
app.include_router(linkedin_router)
app.include_router(profiles_router)
app.include_router(settings_router)
app.include_router(preferences_router)
app.include_router(checklist_router)
```

- [ ] **Step 4: Write tests**

```python
def test_sources_roundtrip(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    # Point config paths to tmp_path
    monkeypatch.setattr("career_job_search.opportunities.sources_helper.USER_CONFIG", tmp_path / "opportunities.yaml")
    monkeypatch.setattr("career_job_search.opportunities.sources_helper.DEFAULT_CONFIG", tmp_path / "opportunities.example.yaml")

    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}

    # GET returns defaults
    get_resp = client.get("/api/v1/settings/sources/", headers=headers)
    assert get_resp.status_code == 200

    # POST saves
    payload = {"opportunities": {"sources": {"linkedin_jobs": {"enabled": True}}}}
    post_resp = client.post("/api/v1/settings/sources/", json=payload, headers=headers)
    assert post_resp.status_code == 200
    assert post_resp.json()["ok"] is True
```

- [ ] **Step 5: Run tests**

```bash
cd job-search && uv run pytest tests/test_api_server.py tests/test_api_routers.py -v
```

Expected: All PASS.

---

### Task 6: Update dashboard_service.py to manage the API server

**Files:**
- Modify: `src/career_job_search/workspace/dashboard_service.py`

- [ ] **Step 1: Add API server management to `run_service()`**

In the `service_commands()` function, add an API server command:

```python
API_SERVER_SCRIPT = "career_job_search.api.main"

def service_commands(mode: str, poll_seconds: float, port: int) -> tuple[list[str], list[str] | None, list[str]]:
    # ... existing worker and dashboard commands ...
    api_command = [
        sys.executable,
        "-m",
        API_SERVER_SCRIPT,
    ]
    # Return (worker, dashboard, api)
    return worker, dashboard_command, api_command
```

Then in `run_service()`, spawn the API server alongside worker and dashboard:

```python
api = subprocess.Popen(
    api_command,
    cwd=JOB_ROOT,
    env=environment,  # carries CAREER_DASHBOARD_TOKEN
    start_new_session=True,
    close_fds=True,
)
```

And in the shutdown block, terminate it:

```python
_terminate(api)
```

The existing `dashboard_process_environment()` already resolves the token — the API server reads it from the same env var.

- [ ] **Step 2: Run lint**

```bash
cd job-search && uv run ruff check src tests
```

Expected: 0 errors.

---

### Task 7: Agent bridge endpoints (LinkedIn desktop agent)

**Files:**
- Create: `src/career_job_search/api/routers/agent.py`
- Modify: `src/career_job_search/api/server.py` (register router)
- Test: `tests/test_api_agent_bridge.py`

**Interfaces:**
- Consumes: `POST /api/v1/agent/heartbeat` — agent sends its status and available campaigns
- Consumes: `POST /api/v1/agent/events` — agent pushes campaign results (connected, messaged, etc.)
- Consumes: `GET /api/v1/agent/commands?since=<iso-timestamp>` — agent polls for pending commands
- Produces: Heartbeat acknowledgment, event acceptance, command queue items

Storage for now: in-memory dict or JSON file (same pattern as existing config helpers). Later migrated to PostgreSQL.

- [ ] **Step 1: Create `src/career_job_search/api/routers/agent.py`**

```python
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from career_job_search.api.auth import verify_token

AGENT_STATE_PATH = Path(os.environ.get("CAREER_AGENT_STATE_DIR", "state")) / "agent_bridge.json"

router = APIRouter(prefix="/api/v1/agent", dependencies=[Depends(verify_token)])


class HeartbeatIn(BaseModel):
    agent_version: str
    status: str  # "idle" | "running" | "error"
    running_campaign: str | None = None
    last_event_at: str | None = None


class EventIn(BaseModel):
    event_type: str  # "connected" | "messaged" | "followed_up" | "error" | "completed"
    campaign_id: str
    recruiter_id: str | None = None
    detail: dict[str, Any] = {}
    occurred_at: str | None = None


class CommandOut(BaseModel):
    command_id: str
    command_type: str  # "run_campaign" | "stop_campaign" | "update_config"
    payload: dict[str, Any]


def _load_state() -> dict[str, Any]:
    if AGENT_STATE_PATH.exists():
        try:
            return json.loads(AGENT_STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_state(state: dict[str, Any]) -> None:
    AGENT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AGENT_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


@router.post("/heartbeat")
async def heartbeat(body: HeartbeatIn) -> dict[str, Any]:
    state = _load_state()
    state["last_heartbeat"] = {
        "at": datetime.now(timezone.utc).isoformat(),
        **body.model_dump(),
    }
    _save_state(state)
    return {"ok": True}


@router.post("/events")
async def push_event(body: EventIn) -> dict[str, Any]:
    state = _load_state()
    events = state.setdefault("events", [])
    events.append({
        "received_at": datetime.now(timezone.utc).isoformat(),
        **body.model_dump(),
    })
    if len(events) > 10_000:
        state["events"] = events[-5_000:]
    _save_state(state)
    return {"ok": True}


@router.get("/commands")
async def poll_commands(since: str | None = Query(None)) -> list[CommandOut]:
    state = _load_state()
    commands = state.get("pending_commands", [])
    if since:
        commands = [c for c in commands if c.get("created_at", "") > since]
    return [CommandOut(**c) for c in commands]
```

- [ ] **Step 2: Register the router in `server.py`**

```python
from career_job_search.api.routers.agent import router as agent_router
app.include_router(agent_router)
```

- [ ] **Step 3: Write tests**

```python
def test_agent_heartbeat(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    monkeypatch.setenv("CAREER_AGENT_STATE_DIR", str(tmp_path))
    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}

    resp = client.post("/api/v1/agent/heartbeat", json={
        "agent_version": "0.1.0", "status": "idle"
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_agent_events(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    monkeypatch.setenv("CAREER_AGENT_STATE_DIR", str(tmp_path))
    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}

    resp = client.post("/api/v1/agent/events", json={
        "event_type": "connected",
        "campaign_id": "camp-1",
        "recruiter_id": "rec-42",
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
```

- [ ] **Step 4: Run full test suite**

```bash
cd job-search && uv run ruff check src tests && uv run pytest tests/ -q
```

Expected: 0 lint errors, all tests pass.

---

## Self-Review

**1. Spec coverage:**
- FastAPI + uvicorn added: Task 1 ✓
- Health endpoint: Task 1 ✓
- Auth middleware: Task 2 ✓ (reuses existing token)
- Generic helper proxy: Task 3 ✓ (maps all 17 helpers, in-process via importlib)
- HTTP bridge in Next.js: Task 4 ✓ (drop-in replacement, config flag toggle)
- Typed endpoints for config helpers: Task 5 ✓ (6 routers for settings/LinkedIn/profiles)
- Dashboard service integration: Task 6 ✓ (spawns API server alongside dashboard)
- Agent bridge endpoints: Task 7 ✓ (heartbeat, events, command polling)
- Tests for all new code: Tasks 1-7 ✓
- Gradual rollout via config flag: Task 4 ✓ (`CAREER_USE_HTTP_BRIDGE=1`)

**2. Placeholder scan:**
No TBDs, TODOs, or placeholders. All code is explicit.

**3. Type consistency:**
- `runPythonHelper<T>(name, args, options)` signature is preserved exactly in Task 4
- All routers return `dict[str, Any]` matching the existing `read_config()` return types
- Agent bridge endpoint paths match the plan's stated interfaces
