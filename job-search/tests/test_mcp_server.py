"""Tests for the Career MCP server."""

from __future__ import annotations

import importlib.util
import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

from career_job_search.integrations.linkedin.campaign import cfg_matching, load_config
from career_job_search.integrations.linkedin.paths import DEFAULT_LINKEDIN_CONFIG
from career_job_search.recruiters.matching import (
    match_recruiter_profile,
    should_send_recruiter_connection,
)


def load_server_module():
    path = Path(__file__).resolve().parents[1] / "mcp" / "server.py"
    spec = importlib.util.spec_from_file_location("career_mcp_server_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_score_recruiter_payload_shape() -> None:
    server = load_server_module()
    payload = server.score_recruiter_payload(
        {
            "headline": "Talent Acquisition Manager",
            "name": "Jane Doe",
            "profile_url": "https://www.linkedin.com/in/jane-doe/",
            "company": "Apranga",
            "about": "Hiring premium retail leaders in Vilnius",
            "role_text": "Head of People",
            "location": "Vilnius, Lithuania",
        }
    )
    assert isinstance(payload, dict)
    assert "would_send" in payload
    assert "primary_score" in payload
    assert "skip_reason" in payload


def test_score_recruiter_payload_matches_linkedin_config_decision() -> None:
    server = load_server_module()
    profile = {
        "headline": (
            "Talent Acquisition Manager luxury premium retail fashion boutique "
            "store director area manager"
        ),
        "name": "Jane Doe",
        "profile_url": "https://www.linkedin.com/in/jane-doe/",
        "company": "Universal Recruitment staffing agency",
        "about": (
            "Executive search and staffing agency for premium retail luxury boutique "
            "store director area manager retail director head of retail roles in Vilnius"
        ),
        "role_text": "hiring manager head of people recruiter",
        "location": "Vilnius, Lithuania",
    }

    cfg = load_config(DEFAULT_LINKEDIN_CONFIG)
    matcher = cfg_matching(cfg)
    recruiter_result = match_recruiter_profile(**profile, recruiter_cfg=cfg)
    expected_ok, expected_reason = should_send_recruiter_connection(
        recruiter_result,
        min_primary_score=float(matcher.get("min_primary_score", 12)),
        min_margin_over_second=float(matcher.get("min_margin_over_second", 4.0)),
        require_clear_winner=bool(matcher.get("require_clear_winner", False)),
        require_recruiter_gate=bool(matcher.get("require_recruiter_gate", True)),
        full_cfg=cfg,
    )

    payload = server.score_recruiter_payload(profile)

    assert payload["would_send"] is expected_ok
    assert payload["skip_reason"] == expected_reason


def test_health_endpoint(tmp_path: Path) -> None:
    server = load_server_module()
    httpd = server.HTTPServer(("127.0.0.1", 0), server.MCPHandler)
    host, port = httpd.server_address
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert data["ok"] is True
        assert data["service"] == "career-mcp"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
