"""Trace and verbose logging for Ollama recruiter agents."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from recruiter_linkedin_paths import LLM_TRACE_JSONL, PIPELINE_DIR

_PREVIEW_CHARS = 600


def _llm_block(full_cfg: dict[str, Any]) -> dict[str, Any]:
    block = full_cfg.get("llm") or {}
    return block if isinstance(block, dict) else {}


def trace_enabled(full_cfg: dict[str, Any]) -> bool:
    if os.environ.get("RECRUITER_LLM_TRACE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return True
    return bool(_llm_block(full_cfg).get("trace", False))


def verbose_enabled(full_cfg: dict[str, Any]) -> bool:
    if os.environ.get("RECRUITER_LLM_VERBOSE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return True
    return bool(_llm_block(full_cfg).get("verbose", False))


def trace_path(full_cfg: dict[str, Any]) -> Path:
    raw = _llm_block(full_cfg).get("trace_path")
    if raw:
        path = Path(str(raw))
        if not path.is_absolute():
            path = PIPELINE_DIR.parent / path
        return path
    return LLM_TRACE_JSONL


def _preview(text: str, limit: int = _PREVIEW_CHARS) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _serialize_output(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, (dict, list, str, int, float, bool)):
        return value
    return str(value)


def emit_event(
    full_cfg: dict[str, Any],
    *,
    kind: str,
    message: str = "",
    agent: str = "",
    model: str = "",
    duration_ms: float | None = None,
    ok: bool | None = None,
    system_prompt: str = "",
    user_prompt: str = "",
    output: Any = None,
    error: str = "",
    meta: dict[str, Any] | None = None,
) -> None:
    """Write JSONL trace + optional stdout when enabled."""
    record: dict[str, Any] = {
        "ts": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "kind": kind,
        "message": message,
        "agent": agent,
        "model": model,
        "ok": ok,
        "duration_ms": round(duration_ms, 1) if duration_ms is not None else None,
        "system_prompt_preview": _preview(system_prompt) if system_prompt else "",
        "user_prompt_preview": _preview(user_prompt) if user_prompt else "",
        "output": _serialize_output(output),
        "error": error or "",
        "meta": meta or {},
    }

    if trace_enabled(full_cfg):
        path = trace_path(full_cfg)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    if verbose_enabled(full_cfg):
        _print_event(record)


def _print_event(record: dict[str, Any]) -> None:
    header = f"[llm:{record.get('kind')}]"
    if record.get("agent"):
        header += f" agent={record['agent']}"
    if record.get("model"):
        header += f" model={record['model']}"
    if record.get("duration_ms") is not None:
        header += f" {record['duration_ms']}ms"
    if record.get("ok") is not None:
        header += " ok" if record["ok"] else " FAIL"
    print(header, file=sys.stderr)
    if record.get("message"):
        print(f"  {record['message']}", file=sys.stderr)
    if record.get("user_prompt_preview"):
        print(f"  user: {record['user_prompt_preview']}", file=sys.stderr)
    if record.get("output") is not None:
        out = record["output"]
        if isinstance(out, dict):
            out_text = json.dumps(out, ensure_ascii=False)
        else:
            out_text = str(out)
        print(f"  output: {_preview(out_text, 800)}", file=sys.stderr)
    if record.get("error"):
        print(f"  error: {record['error']}", file=sys.stderr)
    if record.get("meta"):
        meta = {k: v for k, v in record["meta"].items() if v not in (None, "", [], {})}
        if meta:
            print(f"  meta: {json.dumps(meta, ensure_ascii=False)}", file=sys.stderr)


def trace_graph_node(
    full_cfg: dict[str, Any],
    node: str,
    *,
    message: str = "",
    meta: dict[str, Any] | None = None,
) -> None:
    if not (trace_enabled(full_cfg) or verbose_enabled(full_cfg)):
        return
    emit_event(
        full_cfg, kind="graph_node", message=message or node, agent=node, meta=meta
    )


class AgentCallTrace:
    """Context manager for timed agent call tracing."""

    def __init__(
        self,
        full_cfg: dict[str, Any],
        *,
        agent: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.full_cfg = full_cfg
        self.agent = agent
        self.model = model
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.meta = meta or {}
        self._start = 0.0

    def __enter__(self) -> AgentCallTrace:
        self._start = time.perf_counter()
        if verbose_enabled(self.full_cfg):
            emit_event(
                self.full_cfg,
                kind="agent_start",
                agent=self.agent,
                model=self.model,
                message="calling Ollama",
                user_prompt=self.user_prompt,
                system_prompt=self.system_prompt,
                meta=self.meta,
            )
        return self

    def __exit__(self, exc_type, exc, _tb) -> None:
        duration_ms = (time.perf_counter() - self._start) * 1000.0
        if exc_type is not None:
            emit_event(
                self.full_cfg,
                kind="agent_call",
                agent=self.agent,
                model=self.model,
                duration_ms=duration_ms,
                ok=False,
                system_prompt=self.system_prompt,
                user_prompt=self.user_prompt,
                error=str(exc),
                meta=self.meta,
            )
        return None

    def success(self, output: Any) -> None:
        duration_ms = (time.perf_counter() - self._start) * 1000.0
        emit_event(
            self.full_cfg,
            kind="agent_call",
            agent=self.agent,
            model=self.model,
            duration_ms=duration_ms,
            ok=True,
            system_prompt=self.system_prompt,
            user_prompt=self.user_prompt,
            output=output,
            meta=self.meta,
        )

    def failure(self, error: str, *, output: Any = None) -> None:
        duration_ms = (time.perf_counter() - self._start) * 1000.0
        emit_event(
            self.full_cfg,
            kind="agent_call",
            agent=self.agent,
            model=self.model,
            duration_ms=duration_ms,
            ok=False,
            system_prompt=self.system_prompt,
            user_prompt=self.user_prompt,
            output=output,
            error=error,
            meta=self.meta,
        )
