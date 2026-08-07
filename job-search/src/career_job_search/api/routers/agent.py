from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from career_job_search.api.auth import verify_token

AGENT_STATE_PATH = (
    Path(os.environ.get("CAREER_AGENT_STATE_DIR", "state")) / "agent_bridge.json"
)

router = APIRouter(prefix="/api/v1/agent")


class HeartbeatIn(BaseModel):
    agent_version: str
    status: str
    running_campaign: str | None = None
    last_event_at: str | None = None


class EventIn(BaseModel):
    event_type: str
    campaign_id: str
    recruiter_id: str | None = None
    detail: dict[str, Any] = {}
    occurred_at: str | None = None


class CommandOut(BaseModel):
    command_id: str
    command_type: str
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
async def heartbeat(
    body: HeartbeatIn,
    user_id: str = Depends(verify_token),
) -> dict[str, Any]:
    state = _load_state()
    state["last_heartbeat"] = {
        "at": datetime.now(UTC).isoformat(),
        "user_id": user_id,
        **body.model_dump(),
    }
    _save_state(state)
    return {"ok": True}


@router.post("/events")
async def push_event(
    body: EventIn,
    user_id: str = Depends(verify_token),
) -> dict[str, Any]:
    state = _load_state()
    events = state.setdefault("events", [])
    events.append(
        {
            "received_at": datetime.now(UTC).isoformat(),
            "user_id": user_id,
            **body.model_dump(),
        }
    )
    if len(events) > 10_000:
        state["events"] = events[-5_000:]
    _save_state(state)
    return {"ok": True}


@router.get("/commands")
async def poll_commands(
    user_id: str = Depends(verify_token),
    since: str | None = Query(None),
) -> list[dict[str, Any]]:
    state = _load_state()
    commands = state.get("pending_commands", [])
    if since:
        commands = [c for c in commands if c.get("created_at", "") > since]
    return commands
