import uuid
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from resume_job_matcher.api.dependencies import AuthenticatedSession, get_current_auth, require_csrf
from resume_job_matcher.api.schemas import (
    JobDescriptionResponse,
    JobDescriptionSummaryResponse,
    JobFromTextRequest,
    JobRequirementResponse,
    MatchItemResponse,
    MatchRequest,
    MatchResponse,
    MatchSnapshotContent,
)
from resume_job_matcher.application.job_description_service import (
    PARSER_VERSION,
    parse_job_requirements,
)
from resume_job_matcher.domain.job_requirements import TechnologyRequirementValue
from resume_job_matcher.domain.resume_facts import SkillFactValue, parse_fact_value
from resume_job_matcher.infrastructure.db import get_db
from resume_job_matcher.infrastructure.models import (
    JobDescription,
    JobMatch,
    JobRequirement,
    ResumeFact,
    ResumeProfile,
)
from resume_job_matcher.infrastructure.skill_repository import load_skill_dictionary

router = APIRouter(prefix="/api/v1", tags=["jobs", "matches"])

MATCH_ALGORITHM_VERSION = "deterministic-skill-match-v1"


def serialize_requirement(requirement: JobRequirement) -> JobRequirementResponse:
    return JobRequirementResponse(
        id=requirement.id,
        requirement_type=cast(Literal["required", "bonus"], requirement.requirement_type),
        value=TechnologyRequirementValue.model_validate(requirement.value),
        source_text=requirement.source_text,
        source_location=requirement.source_location,
    )


def serialize_job(
    job: JobDescription, requirements: list[JobRequirement]
) -> JobDescriptionResponse:
    return JobDescriptionResponse(
        id=job.id,
        title=job.title,
        source_type=cast(Literal["pasted_text"], job.source_type),
        parser_version=job.parser_version,
        created_at=job.created_at,
        requirements=[serialize_requirement(requirement) for requirement in requirements],
    )


def serialize_job_summary(job: JobDescription) -> JobDescriptionSummaryResponse:
    return JobDescriptionSummaryResponse(
        id=job.id,
        title=job.title,
        source_type=cast(Literal["pasted_text"], job.source_type),
        created_at=job.created_at,
    )


def serialize_match(match: JobMatch) -> MatchResponse:
    content = MatchSnapshotContent.model_validate(match.content)
    return MatchResponse(
        id=match.id,
        resume_profile_id=match.resume_profile_id,
        job_description_id=match.job_description_id,
        algorithm_version=match.algorithm_version,
        created_at=match.created_at,
        **content.model_dump(),
    )


def owned_job(database_session: Session, job_id: uuid.UUID, user_id: uuid.UUID) -> JobDescription:
    job = database_session.execute(
        select(JobDescription).where(JobDescription.id == job_id, JobDescription.user_id == user_id)
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found"
        )
    return job


@router.post(
    "/jobs/from-text", response_model=JobDescriptionResponse, status_code=status.HTTP_201_CREATED
)
def create_job_from_text(
    payload: JobFromTextRequest,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
) -> JobDescriptionResponse:
    parsed_requirements = parse_job_requirements(
        payload.content, load_skill_dictionary(database_session)
    )
    job = JobDescription(
        user_id=auth.user.id,
        source_type="pasted_text",
        title=payload.title,
        content=payload.content,
        parser_version=PARSER_VERSION,
    )
    database_session.add(job)
    database_session.flush()
    requirements = [
        JobRequirement(
            user_id=auth.user.id,
            job_description_id=job.id,
            requirement_type=requirement.requirement_type,
            value=requirement.value.model_dump(),
            source_text=requirement.source_text,
            source_location=requirement.source_location,
        )
        for requirement in parsed_requirements
    ]
    database_session.add_all(requirements)
    database_session.commit()
    return serialize_job(job, requirements)


@router.get("/jobs/{job_id}", response_model=JobDescriptionResponse)
def get_job(
    job_id: uuid.UUID,
    auth: AuthenticatedSession = Depends(get_current_auth),
    database_session: Session = Depends(get_db),
) -> JobDescriptionResponse:
    job = owned_job(database_session, job_id, auth.user.id)
    requirements = list(
        database_session.execute(
            select(JobRequirement)
            .where(
                JobRequirement.job_description_id == job.id,
                JobRequirement.user_id == auth.user.id,
            )
            .order_by(JobRequirement.created_at, JobRequirement.id)
        ).scalars()
    )
    return serialize_job(job, requirements)


@router.get("/jobs", response_model=list[JobDescriptionSummaryResponse])
def list_jobs(
    limit: int = 20,
    offset: int = 0,
    auth: AuthenticatedSession = Depends(get_current_auth),
    database_session: Session = Depends(get_db),
) -> list[JobDescriptionSummaryResponse]:
    if not 1 <= limit <= 50 or offset < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid pagination"
        )
    jobs = list(
        database_session.execute(
            select(JobDescription)
            .where(JobDescription.user_id == auth.user.id)
            .order_by(JobDescription.created_at.desc(), JobDescription.id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    return [serialize_job_summary(job) for job in jobs]


@router.get("/jobs/{job_id}/matches", response_model=list[MatchResponse])
def list_job_matches(
    job_id: uuid.UUID,
    auth: AuthenticatedSession = Depends(get_current_auth),
    database_session: Session = Depends(get_db),
) -> list[MatchResponse]:
    owned_job(database_session, job_id, auth.user.id)
    matches = list(
        database_session.execute(
            select(JobMatch)
            .where(JobMatch.job_description_id == job_id, JobMatch.user_id == auth.user.id)
            .order_by(JobMatch.created_at.desc(), JobMatch.id.desc())
        ).scalars()
    )
    return [serialize_match(match) for match in matches]


@router.post("/matches", response_model=MatchResponse)
def create_match(
    payload: MatchRequest,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
) -> MatchResponse:
    profile = database_session.execute(
        select(ResumeProfile).where(
            ResumeProfile.id == payload.resume_profile_id,
            ResumeProfile.user_id == auth.user.id,
        )
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    if profile.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resume facts must be confirmed before matching",
        )
    job = owned_job(database_session, payload.job_description_id, auth.user.id)
    existing_match = database_session.execute(
        select(JobMatch).where(
            JobMatch.user_id == auth.user.id,
            JobMatch.resume_profile_id == profile.id,
            JobMatch.job_description_id == job.id,
            JobMatch.algorithm_version == MATCH_ALGORITHM_VERSION,
        )
    ).scalar_one_or_none()
    if existing_match is not None:
        return serialize_match(existing_match)
    resume_facts = list(
        database_session.execute(
            select(ResumeFact).where(
                ResumeFact.resume_profile_id == profile.id,
                ResumeFact.user_id == auth.user.id,
                ResumeFact.fact_type == "skill",
                ResumeFact.user_status.in_(("confirmed", "user_corrected")),
            )
        ).scalars()
    )
    skills_by_name = {
        skill_value.name: fact
        for fact in resume_facts
        if isinstance(skill_value := parse_fact_value(fact.value), SkillFactValue)
    }
    requirements = list(
        database_session.execute(
            select(JobRequirement)
            .where(
                JobRequirement.job_description_id == job.id,
                JobRequirement.user_id == auth.user.id,
            )
            .order_by(JobRequirement.created_at, JobRequirement.id)
        ).scalars()
    )
    satisfied: list[MatchItemResponse] = []
    no_evidence: list[MatchItemResponse] = []
    for requirement in requirements:
        requirement_value = TechnologyRequirementValue.model_validate(requirement.value)
        matching_fact = skills_by_name.get(requirement_value.name)
        item = MatchItemResponse(
            job_requirement_id=requirement.id,
            technology=requirement_value.name,
            requirement_type=cast(Literal["required", "bonus"], requirement.requirement_type),
            job_source_text=requirement.source_text,
            result="satisfied" if matching_fact is not None else "no_evidence",
            resume_fact_id=None if matching_fact is None else matching_fact.id,
            resume_source_text=None if matching_fact is None else matching_fact.source_text,
        )
        if matching_fact is None:
            no_evidence.append(item)
        else:
            satisfied.append(item)
    snapshot = MatchSnapshotContent(satisfied=satisfied, no_evidence=no_evidence)
    match = JobMatch(
        user_id=auth.user.id,
        resume_profile_id=profile.id,
        job_description_id=job.id,
        algorithm_version=MATCH_ALGORITHM_VERSION,
        content=snapshot.model_dump(mode="json"),
    )
    database_session.add(match)
    try:
        database_session.commit()
    except IntegrityError:
        database_session.rollback()
        existing_match = database_session.execute(
            select(JobMatch).where(
                JobMatch.user_id == auth.user.id,
                JobMatch.resume_profile_id == profile.id,
                JobMatch.job_description_id == job.id,
                JobMatch.algorithm_version == MATCH_ALGORITHM_VERSION,
            )
        ).scalar_one()
        return serialize_match(existing_match)
    return serialize_match(match)
