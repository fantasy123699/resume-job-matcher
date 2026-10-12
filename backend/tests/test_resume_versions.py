from typing import Any, cast

from fastapi.testclient import TestClient
from test_job_matching import confirm_resume, create_job
from test_resume_import import authenticated_client, csrf_headers, import_text


def create_accepted_suggestion(client: TestClient, profile_id: str, job_id: str) -> dict[str, Any]:
    suggestions = client.post(
        "/api/v1/optimizations",
        json={"resume_profile_id": profile_id, "job_description_id": job_id},
        headers=csrf_headers(client),
    )
    assert suggestions.status_code == 200
    suggestion = cast(list[dict[str, Any]], suggestions.json())[0]
    decision = client.patch(
        f"/api/v1/optimizations/{suggestion['id']}",
        json={"user_decision": "accepted"},
        headers=csrf_headers(client),
    )
    assert decision.status_code == 200
    return suggestion


def test_version_snapshots_confirmed_sections_and_only_accepted_reordering() -> None:
    client = authenticated_client("version-owner@example.test")
    profile_id = confirm_resume(client, import_text(client))
    job = create_job(client)
    accepted_suggestion = create_accepted_suggestion(client, profile_id, str(job["id"]))

    response = client.post(
        "/api/v1/resume-versions",
        json={
            "resume_profile_id": profile_id,
            "job_description_id": job["id"],
            "idempotency_key": "version-snapshot-1",
        },
        headers=csrf_headers(client),
    )
    assert response.status_code == 201
    version = cast(dict[str, Any], response.json())
    assert version["accepted_suggestion_ids"] == [accepted_suggestion["id"]]
    sections = cast(list[dict[str, Any]], version["content"]["sections"])
    assert sections[0]["fact_type"] == "skills"
    assert all(section["fact_type"] != "skill" for section in sections)
    assert any("Python、FastAPI、PostgreSQL" in section["source_text"] for section in sections)

    fetched = client.get(f"/api/v1/resume-versions/{version['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == version


def test_version_requires_confirmation_and_is_private() -> None:
    owner = authenticated_client("version-private@example.test")
    pending_profile = import_text(owner)
    job = create_job(owner)
    pending = owner.post(
        "/api/v1/resume-versions",
        json={
            "resume_profile_id": pending_profile["id"],
            "job_description_id": job["id"],
            "idempotency_key": "pending-version-1",
        },
        headers=csrf_headers(owner),
    )
    assert pending.status_code == 409

    profile_id = confirm_resume(owner, pending_profile)
    created = owner.post(
        "/api/v1/resume-versions",
        json={
            "resume_profile_id": profile_id,
            "job_description_id": job["id"],
            "idempotency_key": "private-version-1",
        },
        headers=csrf_headers(owner),
    )
    assert created.status_code == 201

    other_user = authenticated_client("version-other@example.test")
    assert other_user.get(f"/api/v1/resume-versions/{created.json()['id']}").status_code == 404


def test_version_requires_decisions_for_existing_suggestions() -> None:
    client = authenticated_client("version-review@example.test")
    profile_id = confirm_resume(client, import_text(client))
    job = create_job(client)
    suggestions = client.post(
        "/api/v1/optimizations",
        json={
            "resume_profile_id": profile_id,
            "job_description_id": job["id"],
            "idempotency_key": "review-version-1",
        },
        headers=csrf_headers(client),
    )
    assert suggestions.status_code == 200
    assert suggestions.json()[0]["user_decision"] == "pending"

    response = client.post(
        "/api/v1/resume-versions",
        json={
            "resume_profile_id": profile_id,
            "job_description_id": job["id"],
            "idempotency_key": "review-version-1",
        },
        headers=csrf_headers(client),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Review all optimization suggestions before creating a version"
    )


def test_version_creation_is_idempotent_and_versions_are_listed() -> None:
    client = authenticated_client("version-history@example.test")
    profile_id = confirm_resume(client, import_text(client))
    job = create_job(client)
    payload = {
        "resume_profile_id": profile_id,
        "job_description_id": job["id"],
        "idempotency_key": "version-history-1",
    }

    created = client.post("/api/v1/resume-versions", json=payload, headers=csrf_headers(client))
    repeated = client.post("/api/v1/resume-versions", json=payload, headers=csrf_headers(client))
    assert created.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json()["id"] == created.json()["id"]

    listed = client.get("/api/v1/resume-versions")
    assert listed.status_code == 200
    assert listed.json() == [
        {
            "id": created.json()["id"],
            "job_description_id": job["id"],
            "job_title": job["title"],
            "accepted_suggestion_count": 0,
            "created_at": created.json()["created_at"],
        }
    ]
