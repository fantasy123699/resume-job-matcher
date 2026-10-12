from fastapi.testclient import TestClient
from sqlalchemy import select
from test_resume_import import authenticated_client, csrf_headers

from resume_job_matcher.application.account_deletion_service import process_due_account_deletions
from resume_job_matcher.core.config import get_settings
from resume_job_matcher.infrastructure.db import SessionLocal
from resume_job_matcher.infrastructure.models import AccountDeletionRequest, User


def test_account_deletion_freezes_account_revokes_session_and_requires_password() -> None:
    client = authenticated_client("delete-account@example.test")
    invalid = client.post(
        "/api/v1/auth/account/deletion",
        json={"password": "wrong-password", "confirmation": "DELETE"},
        headers=csrf_headers(client),
    )
    assert invalid.status_code == 401

    deleted = client.post(
        "/api/v1/auth/account/deletion",
        json={"password": "correct-password", "confirmation": "DELETE"},
        headers=csrf_headers(client),
    )
    assert deleted.status_code == 200
    assert deleted.json()["scheduled_for"]
    assert client.get("/api/v1/me").status_code == 401

    fresh_client = TestClient(client.app)
    login = fresh_client.post(
        "/api/v1/auth/login",
        json={"email": "delete-account@example.test", "password": "correct-password"},
    )
    assert login.status_code == 401


def test_due_account_deletion_removes_the_user_after_the_waiting_period() -> None:
    client = authenticated_client("delete-due@example.test")
    response = client.post(
        "/api/v1/auth/account/deletion",
        json={"password": "correct-password", "confirmation": "DELETE"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200

    with SessionLocal.begin() as database_session:
        request = database_session.execute(select(AccountDeletionRequest)).scalar_one()
        request.scheduled_for = request.created_at
    with SessionLocal() as database_session:
        assert process_due_account_deletions(database_session, get_settings()) == 1
        assert (
            database_session.execute(
                select(User).where(User.email == "delete-due@example.test")
            ).first()
            is None
        )
