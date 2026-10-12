from typing import Any, cast

from fastapi.testclient import TestClient
from test_job_matching import confirm_resume, create_job
from test_resume_import import authenticated_client, csrf_headers, import_text


def create_suggestions(client: TestClient, profile_id: str, job_id: str) -> list[dict[str, Any]]:
    response = client.post(
        "/api/v1/optimizations",
        json={"resume_profile_id": profile_id, "job_description_id": job_id},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200
    return cast(list[dict[str, Any]], response.json())


def test_suggestion_is_evidence_backed_idempotent_and_requires_a_decision() -> None:
    client = authenticated_client("optimization-owner@example.test")
    profile_id = confirm_resume(client, import_text(client))
    job = create_job(client)

    suggestions = create_suggestions(client, profile_id, str(job["id"]))
    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion["section"] == "skills"
    assert suggestion["change_type"] == "reorder"
    assert suggestion["risk"] == "low"
    assert suggestion["requires_user_confirmation"] is True
    assert suggestion["user_decision"] == "pending"
    assert suggestion["original_text"] == suggestion["proposed_text"]
    assert "Python" in suggestion["reason"]
    assert len(suggestion["resume_fact_ids"]) == 4
    assert len(suggestion["job_requirement_ids"]) == 3

    repeated = create_suggestions(client, profile_id, str(job["id"]))
    assert repeated == suggestions

    decision = client.patch(
        f"/api/v1/optimizations/{suggestion['id']}",
        json={"user_decision": "accepted"},
        headers=csrf_headers(client),
    )
    assert decision.status_code == 200
    assert decision.json()["user_decision"] == "accepted"


def test_suggestions_do_not_claim_skills_without_resume_evidence_and_are_private() -> None:
    owner = authenticated_client("optimization-private@example.test")
    profile_id = confirm_resume(owner, import_text(owner))
    job = create_job(owner)
    suggestions = create_suggestions(owner, profile_id, str(job["id"]))
    assert all("Docker" not in suggestion["reason"] for suggestion in suggestions)
    assert all("Kubernetes" not in suggestion["reason"] for suggestion in suggestions)

    other_user = authenticated_client("optimization-other@example.test")
    assert other_user.get(f"/api/v1/optimizations/{suggestions[0]['id']}").status_code == 404
    assert (
        other_user.patch(
            f"/api/v1/optimizations/{suggestions[0]['id']}",
            json={"user_decision": "rejected"},
            headers=csrf_headers(other_user),
        ).status_code
        == 404
    )


def test_suggestions_require_a_confirmed_resume() -> None:
    client = authenticated_client("optimization-pending@example.test")
    profile = import_text(client)
    job = create_job(client)
    response = client.post(
        "/api/v1/optimizations",
        json={"resume_profile_id": profile["id"], "job_description_id": job["id"]},
        headers=csrf_headers(client),
    )
    assert response.status_code == 409
