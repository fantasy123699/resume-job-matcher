import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_job_matcher.api.dependencies import AuthenticatedSession, get_current_auth, require_csrf
from resume_job_matcher.api.routes.jobs import owned_job
from resume_job_matcher.api.routes.resumes import owned_profile
from resume_job_matcher.api.schemas import (
    ResumeVersionContent,
    ResumeVersionCreateRequest,
    ResumeVersionResponse,
    ResumeVersionSummaryResponse,
)
from resume_job_matcher.application.resume_version_service import create_resume_version
from resume_job_matcher.infrastructure.db import get_db
from resume_job_matcher.infrastructure.models import ResumeVersion

router = APIRouter(prefix="/api/v1/resume-versions", tags=["resume-versions"])


def serialize_version(version: ResumeVersion) -> ResumeVersionResponse:
    return ResumeVersionResponse(
        id=version.id,
        resume_profile_id=version.resume_profile_id,
        job_description_id=version.job_description_id,
        content=ResumeVersionContent.model_validate(version.content),
        accepted_suggestion_ids=[uuid.UUID(value) for value in version.accepted_suggestion_ids],
        created_at=version.created_at,
    )


def owned_version(
    database_session: Session, version_id: uuid.UUID, user_id: uuid.UUID
) -> ResumeVersion:
    version = database_session.execute(
        select(ResumeVersion).where(
            ResumeVersion.id == version_id,
            ResumeVersion.user_id == user_id,
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resume version not found"
        )
    return version


@router.post("", response_model=ResumeVersionResponse, status_code=status.HTTP_201_CREATED)
def create_version(
    payload: ResumeVersionCreateRequest,
    response: Response,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
) -> ResumeVersionResponse:
    profile = owned_profile(database_session, payload.resume_profile_id, auth.user.id)
    if profile.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resume facts must be confirmed before creating a version",
        )
    job = owned_job(database_session, payload.job_description_id, auth.user.id)
    try:
        version, created = create_resume_version(
            database_session, profile, job, payload.idempotency_key
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return serialize_version(version)


@router.get("", response_model=list[ResumeVersionSummaryResponse])
def list_versions(
    limit: int = 20,
    offset: int = 0,
    auth: AuthenticatedSession = Depends(get_current_auth),
    database_session: Session = Depends(get_db),
) -> list[ResumeVersionSummaryResponse]:
    if not 1 <= limit <= 50 or offset < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid pagination"
        )
    versions = list(
        database_session.execute(
            select(ResumeVersion)
            .where(ResumeVersion.user_id == auth.user.id)
            .order_by(ResumeVersion.created_at.desc(), ResumeVersion.id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    return [
        ResumeVersionSummaryResponse(
            id=version.id,
            job_description_id=version.job_description_id,
            job_title=ResumeVersionContent.model_validate(version.content).job_title,
            accepted_suggestion_count=len(version.accepted_suggestion_ids),
            created_at=version.created_at,
        )
        for version in versions
    ]


@router.get("/{version_id}", response_model=ResumeVersionResponse)
def get_version(
    version_id: uuid.UUID,
    auth: AuthenticatedSession = Depends(get_current_auth),
    database_session: Session = Depends(get_db),
) -> ResumeVersionResponse:
    return serialize_version(owned_version(database_session, version_id, auth.user.id))
