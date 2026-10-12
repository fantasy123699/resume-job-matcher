from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from resume_job_matcher.application.document_export_service import cleanup_expired_exports
from resume_job_matcher.core.config import Settings
from resume_job_matcher.infrastructure.models import (
    AccountDeletionRequest,
    AgentCheckpoint,
    AgentRun,
    DocumentExport,
    EmailVerificationToken,
    Invitation,
    JobDescription,
    JobRequirement,
    OptimizationSuggestion,
    PasswordResetToken,
    ResumeFact,
    ResumeProfile,
    ResumeVersion,
    SessionRecord,
    User,
)

ACCOUNT_DELETION_DELAY = timedelta(days=7)


def schedule_account_deletion(database_session: Session, user: User) -> AccountDeletionRequest:
    existing = database_session.execute(
        select(AccountDeletionRequest).where(AccountDeletionRequest.user_id == user.id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    request = AccountDeletionRequest(
        user_id=user.id,
        scheduled_for=datetime.now(UTC) + ACCOUNT_DELETION_DELAY,
    )
    user.is_active = False
    database_session.execute(
        update(SessionRecord)
        .where(SessionRecord.user_id == user.id, SessionRecord.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    database_session.add(request)
    database_session.commit()
    return request


def process_due_account_deletions(database_session: Session, settings: Settings) -> int:
    cleanup_expired_exports(database_session, settings)
    requests = list(
        database_session.execute(
            select(AccountDeletionRequest).where(
                AccountDeletionRequest.scheduled_for <= datetime.now(UTC)
            )
        ).scalars()
    )
    for request in requests:
        user_id = request.user_id
        exports = list(
            database_session.execute(
                select(DocumentExport).where(DocumentExport.user_id == user_id)
            ).scalars()
        )
        for export in exports:
            (settings.generated_document_dir / export.storage_name).unlink(missing_ok=True)
        database_session.execute(delete(DocumentExport).where(DocumentExport.user_id == user_id))
        database_session.execute(
            delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id)
        )
        database_session.execute(
            delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
        )
        database_session.execute(delete(AgentCheckpoint).where(AgentCheckpoint.user_id == user_id))
        database_session.execute(delete(AgentRun).where(AgentRun.user_id == user_id))
        database_session.execute(
            delete(OptimizationSuggestion).where(OptimizationSuggestion.user_id == user_id)
        )
        database_session.execute(delete(ResumeVersion).where(ResumeVersion.user_id == user_id))
        database_session.execute(delete(JobRequirement).where(JobRequirement.user_id == user_id))
        database_session.execute(delete(JobDescription).where(JobDescription.user_id == user_id))
        database_session.execute(delete(ResumeFact).where(ResumeFact.user_id == user_id))
        database_session.execute(delete(ResumeProfile).where(ResumeProfile.user_id == user_id))
        database_session.execute(delete(SessionRecord).where(SessionRecord.user_id == user_id))
        database_session.execute(
            update(Invitation)
            .where(Invitation.created_by_user_id == user_id)
            .values(created_by_user_id=None)
        )
        database_session.execute(
            delete(AccountDeletionRequest).where(AccountDeletionRequest.id == request.id)
        )
        database_session.execute(delete(User).where(User.id == user_id))
    if requests:
        database_session.commit()
    return len(requests)
