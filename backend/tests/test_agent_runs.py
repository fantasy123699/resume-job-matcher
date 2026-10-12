from typing import Any, cast

from test_job_matching import confirm_resume, create_job
from test_resume_import import authenticated_client, csrf_headers, import_text

from resume_job_matcher.application.agent_run_service import advance_created_agent_runs
from resume_job_matcher.infrastructure.db import SessionLocal


def test_agent_run_persists_its_edit_approval_checkpoint() -> None:
    client = authenticated_client("agent-owner@example.test")
    profile_id = confirm_resume(client, import_text(client))
    job = create_job(client)
    created = client.post(
        "/api/v1/agent-runs",
        json={"resume_profile_id": profile_id, "job_description_id": job["id"]},
        headers=csrf_headers(client),
    )
    assert created.status_code == 201
    run = cast(dict[str, Any], created.json())
    assert run["state"] == "CREATED"

    with SessionLocal() as database_session:
        assert advance_created_agent_runs(database_session) == 1

    waiting = client.get(f"/api/v1/agent-runs/{run['id']}")
    assert waiting.status_code == 200
    run = cast(dict[str, Any], waiting.json())
    assert run["state"] == "WAIT_USER_APPROVE_EDITS"
    assert run["checkpoints"][0]["status"] == "pending"

    blocked = client.post(
        f"/api/v1/agent-runs/{run['id']}/approval",
        json={"decision": "approved"},
        headers=csrf_headers(client),
    )
    assert blocked.status_code == 409

    for suggestion in client.post(
        "/api/v1/optimizations",
        json={"resume_profile_id": profile_id, "job_description_id": job["id"]},
        headers=csrf_headers(client),
    ).json():
        assert (
            client.patch(
                f"/api/v1/optimizations/{suggestion['id']}",
                json={"user_decision": "accepted"},
                headers=csrf_headers(client),
            ).status_code
            == 200
        )
    approved = client.post(
        f"/api/v1/agent-runs/{run['id']}/approval",
        json={"decision": "approved"},
        headers=csrf_headers(client),
    )
    assert approved.status_code == 200
    assert approved.json()["state"] == "COMPLETED"
