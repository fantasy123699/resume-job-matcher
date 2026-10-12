from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from resume_job_matcher.domain.resume_facts import SectionFactValue, parse_fact_value
from resume_job_matcher.infrastructure.models import (
    JobDescription,
    OptimizationSuggestion,
    ResumeFact,
    ResumeProfile,
    ResumeVersion,
)


def create_resume_version(
    database_session: Session,
    profile: ResumeProfile,
    job: JobDescription,
    idempotency_key: str,
) -> tuple[ResumeVersion, bool]:
    """Snapshot confirmed section facts, applying only explicitly accepted layout changes."""

    existing_version = database_session.execute(
        select(ResumeVersion).where(
            ResumeVersion.user_id == profile.user_id,
            ResumeVersion.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()
    if existing_version is not None:
        if (
            existing_version.resume_profile_id != profile.id
            or existing_version.job_description_id != job.id
        ):
            raise ValueError("Idempotency key was already used for a different resume version")
        return existing_version, False

    section_facts = [
        fact
        for fact in database_session.execute(
            select(ResumeFact)
            .where(
                ResumeFact.user_id == profile.user_id,
                ResumeFact.resume_profile_id == profile.id,
                ResumeFact.user_status.in_(("confirmed", "user_corrected")),
            )
            .order_by(ResumeFact.created_at, ResumeFact.id)
        ).scalars()
        if fact.fact_type != "skill" and isinstance(parse_fact_value(fact.value), SectionFactValue)
    ]
    if not section_facts:
        raise ValueError("A confirmed resume requires at least one section")

    pending_suggestion = database_session.execute(
        select(OptimizationSuggestion.id).where(
            OptimizationSuggestion.user_id == profile.user_id,
            OptimizationSuggestion.resume_profile_id == profile.id,
            OptimizationSuggestion.job_description_id == job.id,
            OptimizationSuggestion.user_decision == "pending",
        )
    ).first()
    if pending_suggestion is not None:
        raise ValueError("Review all optimization suggestions before creating a version")

    accepted_suggestions = list(
        database_session.execute(
            select(OptimizationSuggestion)
            .where(
                OptimizationSuggestion.user_id == profile.user_id,
                OptimizationSuggestion.resume_profile_id == profile.id,
                OptimizationSuggestion.job_description_id == job.id,
                OptimizationSuggestion.user_decision == "accepted",
            )
            .order_by(OptimizationSuggestion.created_at, OptimizationSuggestion.id)
        ).scalars()
    )
    accepted_section_ids = [
        suggestion.resume_fact_ids[0]
        for suggestion in accepted_suggestions
        if suggestion.resume_fact_ids
    ]
    prioritized_sections = [
        fact
        for section_id in accepted_section_ids
        for fact in section_facts
        if str(fact.id) == section_id
    ]
    prioritized_ids = {fact.id for fact in prioritized_sections}
    ordered_sections = [
        *prioritized_sections,
        *(fact for fact in section_facts if fact.id not in prioritized_ids),
    ]
    content = {
        "job_title": job.title,
        "sections": [
            {
                "resume_fact_id": str(fact.id),
                "fact_type": fact.fact_type,
                "source_text": fact.source_text,
                "source_location": fact.source_location,
            }
            for fact in ordered_sections
        ],
    }
    version = ResumeVersion(
        user_id=profile.user_id,
        resume_profile_id=profile.id,
        job_description_id=job.id,
        content=content,
        accepted_suggestion_ids=[str(suggestion.id) for suggestion in accepted_suggestions],
        idempotency_key=idempotency_key,
    )
    database_session.add(version)
    try:
        database_session.commit()
    except IntegrityError:
        database_session.rollback()
        existing_version = database_session.execute(
            select(ResumeVersion).where(
                ResumeVersion.user_id == profile.user_id,
                ResumeVersion.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing_version is not None:
            return existing_version, False
        raise
    return version, True
