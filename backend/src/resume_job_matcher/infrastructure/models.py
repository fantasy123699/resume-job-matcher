import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(16), default=UserRole.USER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (
        UniqueConstraint("action", "key_digest", name="uq_auth_rate_limits_action_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    key_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResumeProfile(Base):
    __tablename__ = "resume_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    source_format: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_confirmation")
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ResumeFact(Base):
    __tablename__ = "resume_facts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    resume_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resume_profiles.id"), index=True, nullable=False
    )
    fact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_location: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    user_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_by: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class JobRequirement(Base):
    __tablename__ = "job_requirements"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    job_description_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_descriptions.id"), index=True, nullable=False
    )
    requirement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_location: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SkillAlias(Base):
    """Reference data: which surface forms resolve to which canonical skill.

    The bundled seed in ``domain.skill_dictionary`` is the baseline; rows here
    extend or recategorise it so new market terminology can be added by an
    operator without a code change and a redeploy.
    """

    __tablename__ = "skill_aliases"
    __table_args__ = (
        UniqueConstraint("canonical_name", "alias", name="uq_skill_aliases_canonical_alias"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="approved", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class JobMatch(Base):
    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "resume_profile_id",
            "job_description_id",
            "algorithm_version",
            name="uq_job_matches_user_resume_job_algorithm",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    resume_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resume_profiles.id"), index=True, nullable=False
    )
    job_description_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_descriptions.id"), index=True, nullable=False
    )
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OptimizationSuggestion(Base):
    __tablename__ = "optimization_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    resume_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resume_profiles.id"), index=True, nullable=False
    )
    job_description_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_descriptions.id"), index=True, nullable=False
    )
    section: Mapped[str] = mapped_column(String(32), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_text: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    resume_fact_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    job_requirement_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    risk: Mapped[str] = mapped_column(String(16), nullable=False)
    requires_user_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    user_decision: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "idempotency_key", name="uq_resume_versions_user_idempotency_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    resume_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resume_profiles.id"), index=True, nullable=False
    )
    job_description_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_descriptions.id"), index=True, nullable=False
    )
    content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    accepted_suggestion_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DocumentExport(Base):
    __tablename__ = "document_exports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    resume_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resume_versions.id"), index=True, nullable=False
    )
    file_format: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    download_name: Mapped[str] = mapped_column(String(200), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AccountDeletionRequest(Base):
    __tablename__ = "account_deletion_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    resume_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resume_profiles.id"), index=True, nullable=False
    )
    job_description_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_descriptions.id"), index=True, nullable=False
    )
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    input: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AgentCheckpoint(Base):
    __tablename__ = "agent_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id"), index=True, nullable=False
    )
    checkpoint_type: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    payload: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
