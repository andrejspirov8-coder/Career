#!/usr/bin/env python3
"""Minimal MCP-compatible HTTP server for Career dashboard.

This is intentionally simple: it exposes a single tool endpoint the dashboard
can call. The dashboard can also be extended to use the stdio MCP server later.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import yaml

from career_job_search.integrations.linkedin.paths import DEFAULT_LINKEDIN_CONFIG
from career_job_search.recruiters.matching import (
    match_recruiter_profile,
    should_send_recruiter_connection,
)


def load_recruiter_cfg(path: Path = DEFAULT_LINKEDIN_CONFIG) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise RuntimeError(f"Recruiter config must be a mapping: {path}")
    return data


RECRUITER_CFG = load_recruiter_cfg()
MATCHING_CFG = RECRUITER_CFG.get("matching") or {}

PORT = 8000


def _json_response(
    handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]
) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def score_recruiter_payload(params: dict[str, Any]) -> dict[str, Any]:
    result = match_recruiter_profile(
        headline=str(params.get("headline", "")),
        name=str(params.get("name", "")),
        profile_url=str(params.get("profile_url", "")),
        company=str(params.get("company", "")),
        about=str(params.get("about", "")),
        role_text=str(params.get("role_text", "")),
        location=str(params.get("location", "")),
        recruiter_cfg=RECRUITER_CFG,
    )
    ok, reason = should_send_recruiter_connection(
        result,
        min_primary_score=float(MATCHING_CFG.get("min_primary_score", 12)),
        min_margin_over_second=float(MATCHING_CFG.get("min_margin_over_second", 4)),
        require_clear_winner=bool(MATCHING_CFG.get("require_clear_winner", False)),
        require_recruiter_gate=bool(MATCHING_CFG.get("require_recruiter_gate", True)),
        full_cfg=RECRUITER_CFG,
    )
    rec = result.get("recommendation") or {}
    meta = result.get("recruiter_meta") or {}
    return {
        "variant_slug_best": rec.get("variant_slug"),
        "primary_score": rec.get("primary_score"),
        "confidence": rec.get("confidence"),
        "tier_candidate": result.get("tier_candidate", "tier_1"),
        "recruiter_gate_ok": meta.get("recruiter_gate_ok"),
        "would_send": ok,
        "skip_reason": reason,
        "top_signals": meta.get("top_signals"),
    }


class MCPHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            _json_response(self, 200, {"ok": True, "service": "career-mcp"})
            return
        _json_response(self, 404, {"error": "Not found"})

    def do_POST(self) -> None:
        if not self.path.startswith("/tools/"):
            _json_response(self, 404, {"error": "Not found"})
            return

        tool = self.path.split("/tools/", 1)[1]
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        params = json.loads(body.decode("utf-8") or "{}")

        if tool == "score_recruiter":
            _json_response(self, 200, score_recruiter_payload(params))
            return

        _json_response(self, 404, {"error": f"Unknown tool: {tool}"})

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    server = HTTPServer(("127.0.0.1", PORT), MCPHandler)
    print(f"Career MCP server listening on http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
