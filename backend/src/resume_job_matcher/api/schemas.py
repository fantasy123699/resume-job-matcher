import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from resume_job_matcher.domain.job_requirements import TechnologyRequirementValue
from resume_job_matcher.domain.resume_facts import FactValue


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    invitation_code: str = Field(min_length=12, max_length=128)
    is_adult: Literal[True]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized.count("@") != 1 or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("A valid email address is required")
        return normalized


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class TokenConfirmRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized.count("@") != 1 or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("A valid email address is required")
        return normalized


class PasswordResetConfirmRequest(TokenConfirmRequest):
    password: str = Field(min_length=12, max_length=128)


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: Literal["user", "admin"]
    email_verified: bool
    created_at: datetime


class InvitationCreateRequest(BaseModel):
    max_uses: int = Field(default=1, ge=1, le=1000)
    expires_in_days: int = Field(default=30, ge=1, le=365)


class InvitationCreateResponse(BaseModel):
    id: uuid.UUID
    code: str
    max_uses: int
    expires_at: datetime


class ErrorResponse(BaseModel):
    code: str
    message: str


class ResumeFactResponse(BaseModel):
    id: uuid.UUID
    fact_type: str
    value: FactValue
    source_text: str
    source_location: str
    confidence: float
    user_status: Literal["pending", "confirmed", "user_corrected", "rejected"]
    created_by: str


class ResumeResponse(BaseModel):
    id: uuid.UUID
    source_format: Literal["text", "docx", "pdf"]
    status: Literal["pending_confirmation", "confirmed"]
    parser_version: str
    created_at: datetime
    facts: list[ResumeFactResponse]


class ResumeFactUpdateRequest(BaseModel):
    user_status: Literal["confirmed", "user_corrected", "rejected"]
    value: FactValue | None = None


class ResumeSummaryResponse(BaseModel):
    id: uuid.UUID
    source_format: Literal["text", "docx", "pdf"]
    status: Literal["pending_confirmation", "confirmed"]
    parser_version: str
    created_at: datetime


class JobFromTextRequest(BaseModel):
    title: str = Field(default="未命名岗位", min_length=1, max_length=200)
    content: str = Field(min_length=80, max_length=100_000)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Job description cannot be empty")
        return normalized


class JobRequirementResponse(BaseModel):
    id: uuid.UUID
    requirement_type: Literal["required", "bonus"]
    value: TechnologyRequirementValue
    source_text: str
    source_location: str


class JobDescriptionResponse(BaseModel):
    id: uuid.UUID
    title: str
    source_type: Literal["pasted_text"]
    parser_version: str
    created_at: datetime
    requirements: list[JobRequirementResponse]


class JobDescriptionSummaryResponse(BaseModel):
    id: uuid.UUID
    title: str
    source_type: Literal["pasted_text"]
    created_at: datetime


class MatchRequest(BaseModel):
    resume_profile_id: uuid.UUID
    job_description_id: uuid.UUID


class MatchItemResponse(BaseModel):
    job_requirement_id: uuid.UUID
    technology: str
    requirement_type: Literal["required", "bonus"]
    job_source_text: str
    result: Literal["satisfied", "no_evidence"]
    resume_fact_id: uuid.UUID | None
    resume_source_text: str | None


class MatchSnapshotContent(BaseModel):
    satisfied: list[MatchItemResponse]
    no_evidence: list[MatchItemResponse]


class MatchResponse(BaseModel):
    id: uuid.UUID
    resume_profile_id: uuid.UUID
    job_description_id: uuid.UUID
    algorithm_version: str
    created_at: datetime
    satisfied: list[MatchItemResponse]
    no_evidence: list[MatchItemResponse]


class OptimizationSuggestionResponse(BaseModel):
    id: uuid.UUID
    resume_profile_id: uuid.UUID
    job_description_id: uuid.UUID
    section: Literal["skills"]
    original_text: str
    proposed_text: str
    change_type: Literal["reorder"]
    reason: str
    resume_fact_ids: list[uuid.UUID] = Field(min_length=1)
    job_requirement_ids: list[uuid.UUID] = Field(min_length=1)
    risk: Literal["low"]
    requires_user_confirmation: Literal[True]
    user_decision: Literal["pending", "accepted", "rejected"]
    created_at: datetime
    updated_at: datetime


class OptimizationRequest(BaseModel):
    resume_profile_id: uuid.UUID
    job_description_id: uuid.UUID


class OptimizationSuggestionDecisionRequest(BaseModel):
    user_decision: Literal["accepted", "rejected"]


class ResumeVersionSection(BaseModel):
    resume_fact_id: uuid.UUID
    fact_type: str
    source_text: str = Field(min_length=1)
    source_location: str = Field(min_length=1)


class ResumeVersionContent(BaseModel):
    job_title: str = Field(min_length=1, max_length=200)
    sections: list[ResumeVersionSection] = Field(min_length=1)


class ResumeVersionCreateRequest(BaseModel):
    resume_profile_id: uuid.UUID
    job_description_id: uuid.UUID
    idempotency_key: str = Field(min_length=1, max_length=128)


class ResumeVersionResponse(BaseModel):
    id: uuid.UUID
    resume_profile_id: uuid.UUID
    job_description_id: uuid.UUID
    content: ResumeVersionContent
    accepted_suggestion_ids: list[uuid.UUID]
    created_at: datetime


class ResumeVersionSummaryResponse(BaseModel):
    id: uuid.UUID
    job_description_id: uuid.UUID
    job_title: str
    accepted_suggestion_count: int = Field(ge=0)
    created_at: datetime


class DocumentExportResponse(BaseModel):
    id: uuid.UUID
    resume_version_id: uuid.UUID
    file_format: Literal["docx"]
    download_url: str
    expires_at: datetime


class AccountDeletionRequestPayload(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    confirmation: Literal["DELETE"]


class AccountDeletionResponse(BaseModel):
    scheduled_for: datetime


class AgentRunCreateRequest(BaseModel):
    resume_profile_id: uuid.UUID
    job_description_id: uuid.UUID


class AgentCheckpointResponse(BaseModel):
    id: uuid.UUID
    checkpoint_type: Literal["edit_approval"]
    status: Literal["pending", "approved", "rejected"]
    payload: dict[str, str]
    created_at: datetime
    updated_at: datetime


class AgentRunResponse(BaseModel):
    id: uuid.UUID
    resume_profile_id: uuid.UUID
    job_description_id: uuid.UUID
    run_type: Literal["resume_optimization"]
    state: Literal["CREATED", "WAIT_USER_APPROVE_EDITS", "COMPLETED", "CANCELLED"]
    attempt_count: int
    max_attempts: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    checkpoints: list[AgentCheckpointResponse]


class AgentCheckpointDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
