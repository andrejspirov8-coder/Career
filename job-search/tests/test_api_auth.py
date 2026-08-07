from __future__ import annotations

from fastapi.testclient import TestClient

from career_job_search.api.server import create_app


def test_missing_dashboard_token_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("CAREER_DASHBOARD_TOKEN", raising=False)
    response = TestClient(create_app()).get(
        "/api/v1/me", headers={"Authorization": "Bearer local-dev"}
    )
    assert response.status_code == 503
    assert "CAREER_DASHBOARD_TOKEN" in response.json()["detail"]


def test_supabase_jwt_is_not_an_api_fallback(monkeypatch) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "expected-token")
    response = TestClient(create_app()).get(
        "/api/v1/me",
        headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.fake.signature"},
    )
    assert response.status_code == 403


def test_signup_requires_feature_flag_and_bearer_auth(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "expected-token")
    monkeypatch.setattr(
        "career_job_search.api.user_store.USERS_DB_PATH", tmp_path / "users.sqlite3"
    )
    client = TestClient(create_app())
    payload = {"email": "owner@example.com", "password": "secure-pass-123"}

    assert client.post("/api/v1/auth/signup", json=payload).status_code == 401

    response = client.post(
        "/api/v1/auth/signup",
        json=payload,
        headers={"Authorization": "Bearer expected-token"},
    )
    assert response.status_code == 403

    monkeypatch.setenv("CAREER_ALLOW_LOCAL_SIGNUP", "true")
    response = client.post(
        "/api/v1/auth/signup",
        json=payload,
        headers={"Authorization": "Bearer expected-token"},
    )
    assert response.status_code == 200


def test_local_login_does_not_issue_supabase_access_token(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("CAREER_DASHBOARD_TOKEN", "expected-token")
    monkeypatch.setenv("CAREER_ALLOW_LOCAL_SIGNUP", "true")
    monkeypatch.setattr(
        "career_job_search.api.user_store.USERS_DB_PATH", tmp_path / "users.sqlite3"
    )
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer expected-token"}
    payload = {"email": "local@example.com", "password": "secure-pass-123"}
    assert (
        client.post("/api/v1/auth/signup", json=payload, headers=headers).status_code
        == 200
    )

    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    assert "supabase_access_token" not in response.json()
