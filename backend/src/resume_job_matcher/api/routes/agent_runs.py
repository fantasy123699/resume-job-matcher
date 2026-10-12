import uuid
from datetime import UTC, datetime
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_job_matcher.api.dependencies import AuthenticatedSession, get_current_auth, require_csrf
from resume_job_matcher.api.routes.jobs import owned_job
from resume_job_matcher.api.routes.resumes import owned_profile
from resume_job_matcher.api.schemas import (
    AgentCheckpointDecisionRequest,
    AgentCheckpointResponse,
    AgentRunCreateRequest,
    AgentRunResponse,
)
from resume_job_matcher.infrastructure.db import get_db
from resume_job_matcher.infrastructure.models import (
    AgentCheckpoint,
    AgentRun,
    OptimizationSuggestion,
)

router = APIRouter(prefix="/api/v1/agent-runs", tags=["agent-runs"])


def serialize_run(database_session: Session, run: AgentRun) -> AgentRunResponse:
    checkpoints = list(
        database_session.execute(
            select(AgentCheckpoint)
            .where(AgentCheckpoint.agent_run_id == run.id, AgentCheckpoint.user_id == run.user_id)
            .order_by(AgentCheckpoint.created_at, AgentCheckpoint.id)
        ).scalars()
    )
    return AgentRunResponse(
        id=run.id,
        resume_profile_id=run.resume_profile_id,
        job_description_id=run.job_description_id,
        run_type=cast(Literal["resume_optimization"], run.run_type),
        state=cast(
            Literal["CREATED", "WAIT_USER_APPROVE_EDITS", "COMPLETED", "CANCELLED"], run.state
        ),
        attempt_count=run.attempt_count,
        max_attempts=run.max_attempts,
        last_error=run.last_error,
        created_at=run.created_at,
        updated_at=run.updated_at,
        checkpoints=[
            AgentCheckpointResponse(
                id=checkpoint.id,
                checkpoint_type=cast(Literal["edit_approval"], checkpoint.checkpoint_type),
                status=cast(Literal["pending", "approved", "rejected"], checkpoint.status),
                payload=checkpoint.payload,
                created_at=checkpoint.created_at,
                updated_at=checkpoint.updated_at,
            )
            for checkpoint in checkpoints
        ],
    )


def owned_run(database_session: Session, run_id: uuid.UUID, user_id: uuid.UUID) -> AgentRun:
    run = database_session.execute(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    return run


@router.post("", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
def create_agent_run(
    payload: AgentRunCreateRequest,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
) -> AgentRunResponse:
    profile = owned_profile(database_session, payload.resume_profile_id, auth.user.id)
    if profile.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resume facts must be confirmed before creating an agent run",
        )
    owned_job(database_session, payload.job_description_id, auth.user.id)
    run = AgentRun(
        user_id=auth.user.id,
        resume_profile_id=profile.id,
        job_description_id=payload.job_description_id,
        run_type="resume_optimization",
        state="CREATED",
        input={"mode": "pasted_job_optimization"},
    )
    database_session.add(run)
    database_session.commit()
    return serialize_run(database_session, run)


@router.get("/{run_id}", response_model=AgentRunResponse)
def get_agent_run(
    run_id: uuid.UUID,
    auth: AuthenticatedSession = Depends(get_current_auth),
    database_session: Session = Depends(get_db),
) -> AgentRunResponse:
    return serialize_run(database_session, owned_run(database_session, run_id, auth.user.id))


@router.post("/{run_id}/approval", response_model=AgentRunResponse)
def decide_agent_run(
    run_id: uuid.UUID,
    payload: AgentCheckpointDecisionRequest,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
) -> AgentRunResponse:
    run = owned_run(database_session, run_id, auth.user.id)
    if run.state != "WAIT_USER_APPROVE_EDITS":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Agent run is not awaiting approval"
        )
    pending_suggestions = database_session.execute(
        select(OptimizationSuggestion.id).where(
            OptimizationSuggestion.user_id == auth.user.id,
            OptimizationSuggestion.resume_profile_id == run.resume_profile_id,
            OptimizationSuggestion.job_description_id == run.job_description_id,
            OptimizationSuggestion.user_decision == "pending",
        )
    ).first()
    if pending_suggestions is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Review every optimization suggestion before approving the run",
        )
    checkpoint = database_session.execute(
        select(AgentCheckpoint)
        .where(
            AgentCheckpoint.agent_run_id == run.id,
            AgentCheckpoint.user_id == auth.user.id,
            AgentCheckpoint.status == "pending",
        )
        .with_for_update()
    ).scalar_one_or_none()
    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Approval checkpoint is unavailable"
        )
    checkpoint.status = payload.decision
    run.state = "COMPLETED" if payload.decision == "approved" else "CANCELLED"
    run.completed_at = datetime.now(UTC)
    database_session.commit()
    return serialize_run(database_session, run)
