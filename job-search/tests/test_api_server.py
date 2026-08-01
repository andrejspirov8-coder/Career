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


def test_auth_missing_header() -> None:
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_auth_valid_token(monkeypatch) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    app = create_app()
    client = TestClient(app)
    response = client.get(
        "/api/v1/me", headers={"Authorization": "Bearer test-token"}
    )
    assert response.status_code == 200
    assert response.json()["user"] == "local-user"


def test_auth_invalid_token(monkeypatch) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    app = create_app()
    client = TestClient(app)
    response = client.get(
        "/api/v1/me", headers={"Authorization": "Bearer wrong-token"}
    )
    assert response.status_code == 403


def test_helper_proxy_valid(monkeypatch) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/api/v1/helpers/opportunitySources",
        json={"args": ["show"]},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["schema"] == "career_python_helper_v1"


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


def test_sources_roundtrip(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    monkeypatch.setattr(
        "career_job_search.opportunities.sources_helper.USER_CONFIG",
        tmp_path / "opportunities.yaml",
    )
    monkeypatch.setattr(
        "career_job_search.opportunities.sources_helper.DEFAULT_CONFIG",
        tmp_path / "opportunities.example.yaml",
    )
    from fastapi.testclient import TestClient

    from career_job_search.api.server import create_app

    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}
    payload = {"opportunities": {"sources": {"linkedin_jobs": {"enabled": True}}}}
    post_resp = client.post("/api/v1/settings/sources/", json=payload, headers=headers)
    assert post_resp.status_code == 200
    get_resp = client.get("/api/v1/settings/sources/", headers=headers)
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert (
        data.get("opportunities", {})
        .get("sources", {})
        .get("linkedin_jobs", {})
        .get("enabled")
        is True
    )


def test_agent_heartbeat(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    monkeypatch.setenv("CAREER_AGENT_STATE_DIR", str(tmp_path))
    from fastapi.testclient import TestClient

    from career_job_search.api.server import create_app

    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}
    resp = client.post(
        "/api/v1/agent/heartbeat",
        json={"agent_version": "0.1.0", "status": "idle"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_auth_signup_and_login(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    monkeypatch.setattr("career_job_search.api.user_store.USERS_DB_PATH", tmp_path / "users.sqlite3")
    from fastapi.testclient import TestClient

    from career_job_search.api.server import create_app
    app = create_app()
    client = TestClient(app)

    signup_resp = client.post("/api/v1/auth/signup", json={"email": "alice@example.com", "password": "secure-pass-123"})
    assert signup_resp.status_code == 200
    data = signup_resp.json()
    assert data["ok"] is True
    user_id = data["user_id"]

    login_resp = client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "secure-pass-123"})
    assert login_resp.status_code == 200
    assert login_resp.json()["user_id"] == user_id

    bad_resp = client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "wrong"})
    assert bad_resp.status_code == 401


def test_auth_me_with_bearer(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    monkeypatch.setattr("career_job_search.api.user_store.USERS_DB_PATH", tmp_path / "users.sqlite3")
    from fastapi.testclient import TestClient

    from career_job_search.api.server import create_app
    from career_job_search.api.user_store import create_user
    create_user("bob@example.com", "password-123")
    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}
    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200


def test_signup_validation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    monkeypatch.setattr("career_job_search.api.user_store.USERS_DB_PATH", tmp_path / "users.sqlite3")
    from fastapi.testclient import TestClient

    from career_job_search.api.server import create_app
    app = create_app()
    client = TestClient(app)

    resp = client.post("/api/v1/auth/signup", json={"email": "not-an-email", "password": "12345678"})
    assert resp.status_code == 400

    resp = client.post("/api/v1/auth/signup", json={"email": "a@b.com", "password": "short"})
    assert resp.status_code == 400


def test_agent_events(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    monkeypatch.setenv("CAREER_AGENT_STATE_DIR", str(tmp_path))
    from fastapi.testclient import TestClient

    from career_job_search.api.server import create_app

    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}
    resp = client.post(
        "/api/v1/agent/events",
        json={
            "event_type": "connected",
            "campaign_id": "camp-1",
            "recruiter_id": "rec-42",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_bearer_token_ignores_cookies(monkeypatch) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "test-token")
    from fastapi.testclient import TestClient

    from career_job_search.api.server import create_app

    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}
    resp = client.get("/api/v1/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["user"] == "local-user"

    resp_no_auth = client.get("/api/v1/me")
    assert resp_no_auth.status_code == 401
