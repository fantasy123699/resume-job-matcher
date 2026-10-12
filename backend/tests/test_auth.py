from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from resume_job_matcher.api.routes import auth as auth_routes
from resume_job_matcher.application.auth_service import create_invitation
from resume_job_matcher.core.config import get_settings
from resume_job_matcher.core.security import hash_password, utc_now
from resume_job_matcher.infrastructure.db import SessionLocal
from resume_job_matcher.infrastructure.models import Invitation, User, UserRole


def create_admin() -> None:
    with SessionLocal.begin() as database_session:
        database_session.add(
            User(
                email="admin@example.test",
                password_hash=hash_password("correct-password"),
                role=UserRole.ADMIN.value,
            )
        )


def create_invite() -> str:
    with SessionLocal.begin() as database_session:
        _, code = create_invitation(
            database_session,
            get_settings(),
            created_by=None,
            max_uses=1,
            expires_in_days=1,
        )
        return code


def register(client: TestClient, invitation_code: str, email: str = "user@example.test") -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-password",
            "invitation_code": invitation_code,
            "is_adult": True,
        },
    )
    assert response.status_code == 201


def login_admin(client: TestClient) -> None:
    create_admin()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.test", "password": "correct-password"},
    )
    assert response.status_code == 200


def csrf_headers(client: TestClient) -> dict[str, str]:
    csrf_token = client.cookies.get("rjm_csrf")
    assert csrf_token is not None
    return {"X-CSRF-Token": csrf_token}


def test_registration_creates_revocable_server_session(client: TestClient) -> None:
    register(client, create_invite())

    me_response = client.get("/api/v1/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "user@example.test"

    missing_csrf = client.post("/api/v1/auth/logout")
    assert missing_csrf.status_code == 403
    logout_response = client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert logout_response.status_code == 204
    assert client.get("/api/v1/me").status_code == 401


def test_session_refresh_rotates_and_revokes_the_previous_token(client: TestClient) -> None:
    register(client, create_invite())
    previous_token = client.cookies.get("rjm_session")
    assert previous_token is not None

    refresh_response = client.post("/api/v1/auth/session/refresh", headers=csrf_headers(client))
    assert refresh_response.status_code == 200
    assert client.cookies.get("rjm_session") != previous_token

    previous_session_client = TestClient(client.app)
    previous_session_client.cookies.set("rjm_session", previous_token)
    assert previous_session_client.get("/api/v1/me").status_code == 401


def test_login_rate_limit_blocks_the_eleventh_attempt(client: TestClient) -> None:
    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "unknown@example.test", "password": "wrong-password"},
        )
        assert response.status_code == 401
    blocked_response = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.test", "password": "wrong-password"},
    )
    assert blocked_response.status_code == 429


def test_invitation_can_only_be_created_by_admin_with_csrf(client: TestClient) -> None:
    register(client, create_invite())
    forbidden_response = client.post("/api/v1/admin/invitations", headers=csrf_headers(client))
    assert forbidden_response.status_code == 403

    client.cookies.clear()
    login_admin(client)
    invitation_response = client.post(
        "/api/v1/admin/invitations",
        headers=csrf_headers(client),
        json={"max_uses": 2, "expires_in_days": 7},
    )
    assert invitation_response.status_code == 201
    assert invitation_response.json()["code"].startswith("rjm_")
    assert invitation_response.json()["max_uses"] == 2


def test_invalid_login_is_non_enumerating(client: TestClient) -> None:
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.test", "password": "wrong-password"},
    )
    with SessionLocal.begin() as database_session:
        database_session.add(
            User(email="known@example.test", password_hash=hash_password("correct-password"))
        )
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": "known@example.test", "password": "wrong-password"},
    )
    assert unknown.status_code == wrong_password.status_code == 401
    assert unknown.json() == wrong_password.json()


def test_invalid_or_expired_invitation_is_rejected(client: TestClient) -> None:
    with SessionLocal.begin() as database_session:
        database_session.add(
            Invitation(
                code_digest="a" * 64,
                max_uses=1,
                expires_at=utc_now() - timedelta(minutes=1),
            )
        )
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.test",
            "password": "correct-password",
            "invitation_code": "expired-code",
            "is_adult": True,
        },
    )
    assert response.status_code == 400


def test_email_verification_requires_a_one_time_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    register(client, create_invite())
    sent_tokens: list[str] = []
    monkeypatch.setattr(
        auth_routes,
        "send_verification_email",
        lambda _settings, _user, token: sent_tokens.append(token),
    )

    request_response = client.post(
        "/api/v1/auth/email-verification/request", headers=csrf_headers(client)
    )
    assert request_response.status_code == 204
    assert len(sent_tokens) == 1

    confirmation_response = client.post(
        "/api/v1/auth/email-verification/confirm", json={"token": sent_tokens[0]}
    )
    assert confirmation_response.status_code == 200
    assert confirmation_response.json()["email_verified"] is True
    assert (
        client.post(
            "/api/v1/auth/email-verification/confirm", json={"token": sent_tokens[0]}
        ).status_code
        == 400
    )


def test_password_reset_is_non_enumerating_and_revokes_sessions(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    register(client, create_invite(), email="reset@example.test")
    sent_tokens: list[str] = []
    monkeypatch.setattr(
        auth_routes,
        "send_password_reset_email",
        lambda _settings, _user, token: sent_tokens.append(token),
    )

    known = client.post("/api/v1/auth/password-reset/request", json={"email": "reset@example.test"})
    unknown = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "unknown@example.test"}
    )
    assert known.status_code == unknown.status_code == 202
    assert len(sent_tokens) == 1

    reset_response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": sent_tokens[0], "password": "new-correct-password"},
    )
    assert reset_response.status_code == 204
    assert client.get("/api/v1/me").status_code == 401

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "reset@example.test", "password": "new-correct-password"},
    )
    assert login_response.status_code == 200
