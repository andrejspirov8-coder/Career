from __future__ import annotations

import httpx


def test_dashboard_server_fixture_works(dashboard_server: str):
    """Dashboard dev server starts and responds on /login."""
    client = httpx.Client(base_url=dashboard_server, timeout=5.0)
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_python_helper_fixture_works(python_helper):
    """Python helper fixture can call automation_control.py overview."""
    result = python_helper("automation_control", ["overview", "--limit", "5"])
    assert result["ok"] is True
    assert "data" in result