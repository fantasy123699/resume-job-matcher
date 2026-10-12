from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_job_matcher.application.optimization_service import create_source_backed_suggestions
from resume_job_matcher.infrastructure.models import (
    AgentCheckpoint,
    AgentRun,
    JobDescription,
    ResumeProfile,
)


def advance_created_agent_runs(database_session: Session, limit: int = 10) -> int:
    runs = list(
        database_session.execute(
            select(AgentRun)
            .where(AgentRun.state == "CREATED")
            .order_by(AgentRun.created_at, AgentRun.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    for run in runs:
        profile = database_session.get(ResumeProfile, run.resume_profile_id)
        job = database_session.get(JobDescription, run.job_description_id)
        if (
            profile is None
            or job is None
            or profile.user_id != run.user_id
            or job.user_id != run.user_id
        ):
            run.state = "CANCELLED"
            run.completed_at = datetime.now(UTC)
            run.last_error = "Referenced resume or job is unavailable"
            continue
        create_source_backed_suggestions(database_session, profile, job)
        run.attempt_count += 1
        run.started_at = run.started_at or datetime.now(UTC)
        run.state = "WAIT_USER_APPROVE_EDITS"
        database_session.add(
            AgentCheckpoint(
                user_id=run.user_id,
                agent_run_id=run.id,
                checkpoint_type="edit_approval",
                status="pending",
                payload={
                    "message": "Review every optimization suggestion before completing this run."
                },
            )
        )
    if runs:
        database_session.commit()
    return len(runs)
