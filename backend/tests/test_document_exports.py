from typing import Any, cast

from test_job_matching import confirm_resume, create_job
from test_resume_import import authenticated_client, csrf_headers, import_text


def test_docx_export_uses_the_version_snapshot_and_is_private() -> None:
    owner = authenticated_client("export-owner@example.test")
    profile_id = confirm_resume(owner, import_text(owner))
    job = create_job(owner)
    version = owner.post(
        "/api/v1/resume-versions",
        json={
            "resume_profile_id": profile_id,
            "job_description_id": job["id"],
            "idempotency_key": "export-version-1",
        },
        headers=csrf_headers(owner),
    )
    assert version.status_code == 201
    version_data = cast(dict[str, Any], version.json())

    exported = owner.post(
        f"/api/v1/resume-versions/{version_data['id']}/exports/docx",
        headers=csrf_headers(owner),
    )
    assert exported.status_code == 200
    export = cast(dict[str, Any], exported.json())
    assert export["file_format"] == "docx"

    downloaded = owner.get(export["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"PK")

    other_user = authenticated_client("export-other@example.test")
    assert other_user.get(export["download_url"]).status_code == 404
