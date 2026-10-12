import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_job_matcher.api.dependencies import AuthenticatedSession, get_current_auth, require_csrf
from resume_job_matcher.api.routes.resume_versions import owned_version
from resume_job_matcher.api.schemas import DocumentExportResponse
from resume_job_matcher.application.document_export_service import create_docx_export
from resume_job_matcher.core.config import Settings, get_settings
from resume_job_matcher.infrastructure.db import get_db
from resume_job_matcher.infrastructure.models import DocumentExport

router = APIRouter(prefix="/api/v1", tags=["exports"])


def serialize_export(export: DocumentExport) -> DocumentExportResponse:
    return DocumentExportResponse(
        id=export.id,
        resume_version_id=export.resume_version_id,
        file_format="docx",
        download_url=f"/api/v1/exports/{export.id}/download",
        expires_at=export.expires_at,
    )


@router.post("/resume-versions/{version_id}/exports/docx", response_model=DocumentExportResponse)
def export_docx(
    version_id: uuid.UUID,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentExportResponse:
    version = owned_version(database_session, version_id, auth.user.id)
    return serialize_export(create_docx_export(database_session, settings, version))


@router.get("/exports/{export_id}/download")
def download_export(
    export_id: uuid.UUID,
    auth: AuthenticatedSession = Depends(get_current_auth),
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    export = database_session.execute(
        select(DocumentExport).where(
            DocumentExport.id == export_id, DocumentExport.user_id == auth.user.id
        )
    ).scalar_one_or_none()
    if export is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    file_path = settings.generated_document_dir / export.storage_name
    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="Export is no longer available"
        )
    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=export.download_name,
    )
