from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_job_matcher.domain.job_requirements import TechnologyRequirementValue
from resume_job_matcher.domain.resume_facts import (
    SectionFactValue,
    SkillFactValue,
    parse_fact_value,
)
from resume_job_matcher.infrastructure.models import (
    JobDescription,
    JobRequirement,
    OptimizationSuggestion,
    ResumeFact,
    ResumeProfile,
)


def create_source_backed_suggestions(
    database_session: Session,
    profile: ResumeProfile,
    job: JobDescription,
) -> list[OptimizationSuggestion]:
    """Create only safe layout suggestions from confirmed, matching skill facts."""

    existing = list(
        database_session.execute(
            select(OptimizationSuggestion)
            .where(
                OptimizationSuggestion.user_id == profile.user_id,
                OptimizationSuggestion.resume_profile_id == profile.id,
                OptimizationSuggestion.job_description_id == job.id,
            )
            .order_by(OptimizationSuggestion.created_at, OptimizationSuggestion.id)
        ).scalars()
    )
    if existing:
        return existing

    facts = list(
        database_session.execute(
            select(ResumeFact).where(
                ResumeFact.user_id == profile.user_id,
                ResumeFact.resume_profile_id == profile.id,
                ResumeFact.user_status.in_(("confirmed", "user_corrected")),
            )
        ).scalars()
    )
    matching_skills = {
        skill_value.name: fact
        for fact in facts
        if fact.fact_type == "skill"
        and isinstance(skill_value := parse_fact_value(fact.value), SkillFactValue)
    }
    required_requirements = [
        requirement
        for requirement in database_session.execute(
            select(JobRequirement)
            .where(
                JobRequirement.user_id == profile.user_id,
                JobRequirement.job_description_id == job.id,
                JobRequirement.requirement_type == "required",
            )
            .order_by(JobRequirement.created_at, JobRequirement.id)
        ).scalars()
        if TechnologyRequirementValue.model_validate(requirement.value).name in matching_skills
    ]
    if not required_requirements:
        return []

    matched_skill_facts = [
        matching_skills[TechnologyRequirementValue.model_validate(requirement.value).name]
        for requirement in required_requirements
    ]
    matched_source_locations = {fact.source_location for fact in matched_skill_facts}
    skill_sections = [
        fact
        for fact in facts
        if fact.fact_type == "skills"
        and isinstance(section_value := parse_fact_value(fact.value), SectionFactValue)
        and section_value.title
        and fact.source_location in matched_source_locations
    ]
    if not skill_sections:
        return []

    technologies = "、".join(
        TechnologyRequirementValue.model_validate(requirement.value).name
        for requirement in required_requirements
    )
    suggestions = [
        OptimizationSuggestion(
            user_id=profile.user_id,
            resume_profile_id=profile.id,
            job_description_id=job.id,
            section="skills",
            original_text=section.source_text,
            proposed_text=section.source_text,
            change_type="reorder",
            reason=f"将技能区段前置，以便直接呈现与该 JD 对应的已确认技能：{technologies}。",
            resume_fact_ids=[str(section.id), *(str(fact.id) for fact in matched_skill_facts)],
            job_requirement_ids=[str(requirement.id) for requirement in required_requirements],
            risk="low",
            requires_user_confirmation=True,
            user_decision="pending",
        )
        for section in skill_sections
    ]
    database_session.add_all(suggestions)
    database_session.commit()
    return suggestions
