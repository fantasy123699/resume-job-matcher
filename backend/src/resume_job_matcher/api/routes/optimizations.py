import uuid
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_job_matcher.api.dependencies import AuthenticatedSession, get_current_auth, require_csrf
from resume_job_matcher.api.routes.jobs import owned_job
from resume_job_matcher.api.routes.resumes import owned_profile
from resume_job_matcher.api.schemas import (
    OptimizationRequest,
    OptimizationSuggestionDecisionRequest,
    OptimizationSuggestionResponse,
)
from resume_job_matcher.application.optimization_service import create_source_backed_suggestions
from resume_job_matcher.infrastructure.db import get_db
from resume_job_matcher.infrastructure.models import OptimizationSuggestion

router = APIRouter(prefix="/api/v1", tags=["optimizations"])


def serialize_suggestion(suggestion: OptimizationSuggestion) -> OptimizationSuggestionResponse:
    return OptimizationSuggestionResponse(
        id=suggestion.id,
        resume_profile_id=suggestion.resume_profile_id,
        job_description_id=suggestion.job_description_id,
        section=cast(Literal["skills"], suggestion.section),
        original_text=suggestion.original_text,
        proposed_text=suggestion.proposed_text,
        change_type=cast(Literal["reorder"], suggestion.change_type),
        reason=suggestion.reason,
        resume_fact_ids=[uuid.UUID(value) for value in suggestion.resume_fact_ids],
        job_requirement_ids=[uuid.UUID(value) for value in suggestion.job_requirement_ids],
        risk=cast(Literal["low"], suggestion.risk),
        requires_user_confirmation=cast(Literal[True], suggestion.requires_user_confirmation),
        user_decision=cast(Literal["pending", "accepted", "rejected"], suggestion.user_decision),
        created_at=suggestion.created_at,
        updated_at=suggestion.updated_at,
    )


def owned_suggestion(
    database_session: Session, suggestion_id: uuid.UUID, user_id: uuid.UUID
) -> OptimizationSuggestion:
    suggestion = database_session.execute(
        select(OptimizationSuggestion).where(
            OptimizationSuggestion.id == suggestion_id,
            OptimizationSuggestion.user_id == user_id,
        )
    ).scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
    return suggestion


@router.get("/optimizations", response_model=list[OptimizationSuggestionResponse])
def list_optimizations(
    resume_profile_id: uuid.UUID,
    job_description_id: uuid.UUID,
    auth: AuthenticatedSession = Depends(get_current_auth),
    database_session: Session = Depends(get_db),
) -> list[OptimizationSuggestionResponse]:
    owned_profile(database_session, resume_profile_id, auth.user.id)
    owned_job(database_session, job_description_id, auth.user.id)
    suggestions = list(
        database_session.execute(
            select(OptimizationSuggestion)
            .where(
                OptimizationSuggestion.user_id == auth.user.id,
                OptimizationSuggestion.resume_profile_id == resume_profile_id,
                OptimizationSuggestion.job_description_id == job_description_id,
            )
            .order_by(OptimizationSuggestion.created_at, OptimizationSuggestion.id)
        ).scalars()
    )
    return [serialize_suggestion(suggestion) for suggestion in suggestions]


@router.post("/optimizations", response_model=list[OptimizationSuggestionResponse])
def create_optimizations(
    payload: OptimizationRequest,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
) -> list[OptimizationSuggestionResponse]:
    profile = owned_profile(database_session, payload.resume_profile_id, auth.user.id)
    if profile.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resume facts must be confirmed before generating suggestions",
        )
    job = owned_job(database_session, payload.job_description_id, auth.user.id)
    suggestions = create_source_backed_suggestions(database_session, profile, job)
    return [serialize_suggestion(suggestion) for suggestion in suggestions]


@router.get("/optimizations/{suggestion_id}", response_model=OptimizationSuggestionResponse)
def get_optimization(
    suggestion_id: uuid.UUID,
    auth: AuthenticatedSession = Depends(get_current_auth),
    database_session: Session = Depends(get_db),
) -> OptimizationSuggestionResponse:
    return serialize_suggestion(owned_suggestion(database_session, suggestion_id, auth.user.id))


@router.patch("/optimizations/{suggestion_id}", response_model=OptimizationSuggestionResponse)
def decide_optimization(
    suggestion_id: uuid.UUID,
    payload: OptimizationSuggestionDecisionRequest,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
) -> OptimizationSuggestionResponse:
    suggestion = owned_suggestion(database_session, suggestion_id, auth.user.id)
    suggestion.user_decision = payload.user_decision
    database_session.commit()
    return serialize_suggestion(suggestion)
