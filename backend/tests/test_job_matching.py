from typing import Any, cast

from fastapi.testclient import TestClient
from test_resume_import import authenticated_client, csrf_headers, import_text


def confirm_resume(client: TestClient, imported: dict[str, Any]) -> str:
    profile_id = str(imported["id"])
    facts = cast(list[dict[str, Any]], imported["facts"])
    for fact in facts:
        response = client.patch(
            f"/api/v1/resumes/{profile_id}/facts/{fact['id']}",
            json={"user_status": "confirmed"},
            headers=csrf_headers(client),
        )
        assert response.status_code == 200
    response = client.post(f"/api/v1/resumes/{profile_id}/confirm", headers=csrf_headers(client))
    assert response.status_code == 200
    return profile_id


def create_job(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v1/jobs/from-text",
        json={
            "title": "后端工程师",
            "content": """岗位职责：参与平台服务开发和维护，保障系统稳定性。
任职要求：熟悉 Python、FastAPI 和 PostgreSQL，具备良好的工程实践能力。
加分项：有 Kubernetes 或 Docker 相关经验。""",
        },
        headers=csrf_headers(client),
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def test_pasted_job_is_matched_only_against_confirmed_resume_skills() -> None:
    client = authenticated_client("match-owner@example.test")
    profile_id = confirm_resume(client, import_text(client))
    job = create_job(client)
    requirements = cast(list[dict[str, Any]], job["requirements"])
    requirement_types = {
        requirement["value"]["name"]: requirement["requirement_type"]
        for requirement in requirements
    }
    assert requirement_types == {
        "Python": "required",
        "FastAPI": "required",
        "PostgreSQL": "required",
        "Docker": "bonus",
        "Kubernetes": "bonus",
    }

    response = client.post(
        "/api/v1/matches",
        json={"resume_profile_id": profile_id, "job_description_id": job["id"]},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200
    match = response.json()
    assert {item["technology"] for item in match["satisfied"]} == {
        "Python",
        "FastAPI",
        "PostgreSQL",
    }
    assert {item["technology"] for item in match["no_evidence"]} == {"Docker", "Kubernetes"}
    assert all(item["result"] == "no_evidence" for item in match["no_evidence"])
    assert all(item["resume_fact_id"] is not None for item in match["satisfied"])


def test_matching_requires_confirmation_and_enforces_job_ownership() -> None:
    owner = authenticated_client("match-pending@example.test")
    imported = import_text(owner)
    job = create_job(owner)
    pending_response = owner.post(
        "/api/v1/matches",
        json={"resume_profile_id": imported["id"], "job_description_id": job["id"]},
        headers=csrf_headers(owner),
    )
    assert pending_response.status_code == 409

    other_user = authenticated_client("match-other@example.test")
    assert other_user.get(f"/api/v1/jobs/{job['id']}").status_code == 404
    hidden_match = other_user.post(
        "/api/v1/matches",
        json={"resume_profile_id": imported["id"], "job_description_id": job["id"]},
        headers=csrf_headers(other_user),
    )
    assert hidden_match.status_code == 404


def test_jobs_are_listed_only_for_their_owner() -> None:
    owner = authenticated_client("job-history@example.test")
    job = create_job(owner)

    listed = owner.get("/api/v1/jobs")
    assert listed.status_code == 200
    assert listed.json() == [
        {
            "id": job["id"],
            "title": job["title"],
            "source_type": "pasted_text",
            "created_at": job["created_at"],
        }
    ]

    other_user = authenticated_client("job-history-other@example.test")
    assert other_user.get("/api/v1/jobs").json() == []


def test_match_snapshots_are_reused_and_keep_their_resume_context() -> None:
    owner = authenticated_client("match-snapshot@example.test")
    first_profile_id = confirm_resume(owner, import_text(owner))
    job = create_job(owner)

    first_match_response = owner.post(
        "/api/v1/matches",
        json={"resume_profile_id": first_profile_id, "job_description_id": job["id"]},
        headers=csrf_headers(owner),
    )
    assert first_match_response.status_code == 200
    first_match = cast(dict[str, Any], first_match_response.json())

    repeated_match_response = owner.post(
        "/api/v1/matches",
        json={"resume_profile_id": first_profile_id, "job_description_id": job["id"]},
        headers=csrf_headers(owner),
    )
    assert repeated_match_response.status_code == 200
    assert repeated_match_response.json()["id"] == first_match["id"]

    second_profile_id = confirm_resume(owner, import_text(owner))
    second_match_response = owner.post(
        "/api/v1/matches",
        json={"resume_profile_id": second_profile_id, "job_description_id": job["id"]},
        headers=csrf_headers(owner),
    )
    assert second_match_response.status_code == 200

    stored_matches = owner.get(f"/api/v1/jobs/{job['id']}/matches")
    assert stored_matches.status_code == 200
    assert {item["resume_profile_id"] for item in stored_matches.json()} == {
        first_profile_id,
        second_profile_id,
    }
    assert all(
        item["algorithm_version"] == "deterministic-skill-match-v1"
        for item in stored_matches.json()
    )

    other_user = authenticated_client("match-snapshot-other@example.test")
    assert other_user.get(f"/api/v1/jobs/{job['id']}/matches").status_code == 404
