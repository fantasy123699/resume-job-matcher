import uuid
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_job_matcher.api.dependencies import AuthenticatedSession, get_current_auth, require_csrf
from resume_job_matcher.api.schemas import (
    ResumeFactResponse,
    ResumeFactUpdateRequest,
    ResumeResponse,
    ResumeSummaryResponse,
)
from resume_job_matcher.application.llm_extraction_service import extract_facts_with_guard
from resume_job_matcher.application.resume_import_service import (
    PARSER_VERSION,
    ParsedFact,
    build_facts,
    determine_file_format,
    extract_source_lines,
    parse_pasted_text,
    temporary_raw_file,
)
from resume_job_matcher.core.config import Settings, get_settings
from resume_job_matcher.domain.resume_facts import (
    SectionFactValue,
    SkillFactValue,
    parse_fact_value,
)
from resume_job_matcher.infrastructure.db import get_db
from resume_job_matcher.infrastructure.llm_provider import build_llm_provider
from resume_job_matcher.infrastructure.models import ResumeFact, ResumeProfile
from resume_job_matcher.infrastructure.skill_repository import load_skill_dictionary

router = APIRouter(prefix="/api/v1/resumes", tags=["resumes"])


def model_facts_from_outcome(outcome: object) -> list[ParsedFact]:
    """Turn guard-accepted proposals into persistable facts.

    Only facts that cleared the guard reach here, so every row carries a quote that
    was verified to exist in the source. The guard's resolved ``source_ref`` is used
    as the location rather than anything the model asserted.
    """

    guard = getattr(outcome, "guard", None)
    if guard is None:
        return []
    facts: list[ParsedFact] = []
    for accepted in guard.accepted:
        facts.append(
            ParsedFact(
                fact_type=accepted.category,
                value=SectionFactValue(title=accepted.statement[:100], content=accepted.quote),
                source_text=accepted.quote,
                source_location=accepted.source_ref,
            )
        )
    return facts


def serialize_fact(fact: ResumeFact) -> ResumeFactResponse:
    return ResumeFactResponse(
        id=fact.id,
        fact_type=fact.fact_type,
        value=parse_fact_value(fact.value),
        source_text=fact.source_text,
        source_location=fact.source_location,
        confidence=fact.confidence,
        user_status=cast(
            Literal["pending", "confirmed", "user_corrected", "rejected"], fact.user_status
        ),
        created_by=fact.created_by,
    )


def serialize_profile(profile: ResumeProfile, facts: list[ResumeFact]) -> ResumeResponse:
    return ResumeResponse(
        id=profile.id,
        source_format=cast(Literal["text", "docx", "pdf"], profile.source_format),
        status=cast(Literal["pending_confirmation", "confirmed"], profile.status),
        parser_version=profile.parser_version,
        created_at=profile.created_at,
        facts=[serialize_fact(fact) for fact in facts],
    )


def serialize_summary(profile: ResumeProfile) -> ResumeSummaryResponse:
    return ResumeSummaryResponse(
        id=profile.id,
        source_format=cast(Literal["text", "docx", "pdf"], profile.source_format),
        status=cast(Literal["pending_confirmation", "confirmed"], profile.status),
        parser_version=profile.parser_version,
        created_at=profile.created_at,
    )


def owned_profile(
    database_session: Session, profile_id: uuid.UUID, user_id: uuid.UUID
) -> ResumeProfile:
    profile = database_session.execute(
        select(ResumeProfile).where(
            ResumeProfile.id == profile_id,
            ResumeProfile.user_id == user_id,
        )
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    return profile


@router.post("/import", response_model=ResumeResponse, status_code=status.HTTP_201_CREATED)
async def import_resume(
    text_content: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ResumeResponse:
    if (text_content is None) == (file is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide exactly one of text_content or file",
        )

    skill_dictionary = load_skill_dictionary(database_session)

    if text_content is not None:
        if len(text_content) > settings.upload_max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Resume text exceeds the size limit",
            )
        source_format = "text"
        source_lines = parse_pasted_text(text_content)
        facts = build_facts(source_lines, skill_dictionary)
    else:
        assert file is not None
        source_format = determine_file_format(file.filename)
        raw_content = await file.read(settings.upload_max_bytes + 1)
        await file.close()
        if len(raw_content) > settings.upload_max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Resume file exceeds the size limit",
            )
        with temporary_raw_file(settings, raw_content, f".{source_format}") as raw_file:
            source_lines = extract_source_lines(raw_file, source_format)
            facts = build_facts(source_lines, skill_dictionary)

    # Model-assisted extraction is additive: the deterministic facts above are always
    # kept, and only proposals that survive the fact guard are appended. A provider
    # that is unconfigured, slow, or wrong therefore costs nothing but recall.
    model_facts: list[ParsedFact] = []
    outcome = extract_facts_with_guard(
        build_llm_provider(settings),
        [(line.location, line.text) for line in source_lines],
        dictionary=skill_dictionary,
    )
    model_facts = model_facts_from_outcome(outcome)
    prepared_facts = [
        (
            fact,
            outcome.model_name if fact in model_facts else "deterministic_parser",
        )
        for fact in [*facts, *model_facts]
    ]

    profile = ResumeProfile(
        user_id=auth.user.id,
        source_format=source_format,
        status="pending_confirmation",
        parser_version=PARSER_VERSION,
    )
    database_session.add(profile)
    database_session.flush()
    persisted_facts = [
        ResumeFact(
            user_id=auth.user.id,
            resume_profile_id=profile.id,
            fact_type=fact.fact_type,
            value=fact.value.model_dump(),
            source_text=fact.source_text,
            source_location=fact.source_location,
            # Model-proposed facts keep the model's name so a reviewer can tell which
            # rows came from the guard path and which from the deterministic parser.
            confidence=1.0 if origin == "deterministic_parser" else 0.9,
            user_status="pending",
            created_by=origin,
        )
        for fact, origin in prepared_facts
    ]
    database_session.add_all(persisted_facts)
    database_session.commit()
    return serialize_profile(profile, persisted_facts)


@router.get("", response_model=list[ResumeSummaryResponse])
def list_resumes(
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    auth: AuthenticatedSession = Depends(get_current_auth),
    database_session: Session = Depends(get_db),
) -> list[ResumeSummaryResponse]:
    profiles = list(
        database_session.execute(
            select(ResumeProfile)
            .where(ResumeProfile.user_id == auth.user.id)
            .order_by(ResumeProfile.created_at.desc(), ResumeProfile.id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    return [serialize_summary(profile) for profile in profiles]


@router.get("/{profile_id}", response_model=ResumeResponse)
def get_resume(
    profile_id: uuid.UUID,
    auth: AuthenticatedSession = Depends(get_current_auth),
    database_session: Session = Depends(get_db),
) -> ResumeResponse:
    profile = owned_profile(database_session, profile_id, auth.user.id)
    facts = list(
        database_session.execute(
            select(ResumeFact)
            .where(ResumeFact.resume_profile_id == profile.id, ResumeFact.user_id == auth.user.id)
            .order_by(ResumeFact.created_at, ResumeFact.id)
        ).scalars()
    )
    return serialize_profile(profile, facts)


@router.patch("/{profile_id}/facts/{fact_id}", response_model=ResumeFactResponse)
def update_fact(
    profile_id: uuid.UUID,
    fact_id: uuid.UUID,
    payload: ResumeFactUpdateRequest,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
) -> ResumeFactResponse:
    profile = owned_profile(database_session, profile_id, auth.user.id)
    fact = database_session.execute(
        select(ResumeFact).where(
            ResumeFact.id == fact_id,
            ResumeFact.resume_profile_id == profile.id,
            ResumeFact.user_id == auth.user.id,
        )
    ).scalar_one_or_none()
    if fact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume fact not found")
    if payload.user_status == "user_corrected" and payload.value is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A corrected fact requires a value",
        )
    if payload.user_status != "user_corrected" and payload.value is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only a user-corrected fact may replace its value",
        )
    if payload.value is not None:
        if fact.fact_type == "skill" and not isinstance(payload.value, SkillFactValue):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A skill fact requires a skill value",
            )
        if fact.fact_type != "skill" and isinstance(payload.value, SkillFactValue):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A section fact requires a section value",
            )
        fact.value = payload.value.model_dump()
    fact.user_status = payload.user_status
    if payload.user_status == "user_corrected":
        fact.created_by = "user"
    database_session.commit()
    return serialize_fact(fact)


@router.post("/{profile_id}/confirm", response_model=ResumeResponse)
def confirm_resume(
    profile_id: uuid.UUID,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
) -> ResumeResponse:
    profile = owned_profile(database_session, profile_id, auth.user.id)
    facts = list(
        database_session.execute(
            select(ResumeFact)
            .where(ResumeFact.resume_profile_id == profile.id, ResumeFact.user_id == auth.user.id)
            .order_by(ResumeFact.created_at, ResumeFact.id)
        ).scalars()
    )
    if any(fact.user_status == "pending" for fact in facts):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="All facts must be reviewed before confirming the resume",
        )
    profile.status = "confirmed"
    database_session.commit()
    return serialize_profile(profile, facts)
