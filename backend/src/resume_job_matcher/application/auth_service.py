from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from resume_job_matcher.api.dependencies import AuthenticatedSession
from resume_job_matcher.core.config import Settings
from resume_job_matcher.core.security import (
    expires_after_hours,
    keyed_digest,
    make_invitation_code,
    make_token,
    utc_now,
)
from resume_job_matcher.infrastructure.models import (
    AuthRateLimit,
    EmailVerificationToken,
    Invitation,
    PasswordResetToken,
    SessionRecord,
    User,
)

RATE_LIMITS = {
    "login": (10, timedelta(minutes=15)),
    "register": (5, timedelta(hours=1)),
    "invitation": (20, timedelta(hours=1)),
    "email_verification": (5, timedelta(hours=1)),
    "password_reset": (5, timedelta(hours=1)),
}


def enforce_rate_limit(
    database_session: Session, settings: Settings, action: str, subject: str
) -> None:
    """Persist a small, per-action limit without introducing another service."""

    maximum, window = RATE_LIMITS[action]
    now = utc_now()
    digest = keyed_digest(settings, f"rate-limit:{action}:{subject}")
    rate_limit = database_session.execute(
        select(AuthRateLimit)
        .where(AuthRateLimit.action == action, AuthRateLimit.key_digest == digest)
        .with_for_update()
    ).scalar_one_or_none()

    if rate_limit is None:
        database_session.add(
            AuthRateLimit(
                action=action,
                key_digest=digest,
                window_started_at=now,
                count=1,
            )
        )
        return

    if now - rate_limit.window_started_at >= window:
        rate_limit.window_started_at = now
        rate_limit.count = 1
        return

    if rate_limit.count >= maximum:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
        )
    rate_limit.count += 1


def consume_invitation(database_session: Session, settings: Settings, code: str) -> Invitation:
    invitation = database_session.execute(
        select(Invitation)
        .where(Invitation.code_digest == keyed_digest(settings, code))
        .with_for_update()
    ).scalar_one_or_none()
    now = utc_now()
    if (
        invitation is None
        or invitation.expires_at <= now
        or invitation.used_count >= invitation.max_uses
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation code is invalid"
        )
    invitation.used_count += 1
    return invitation


def create_invitation(
    database_session: Session,
    settings: Settings,
    created_by: User | None,
    max_uses: int,
    expires_in_days: int,
) -> tuple[Invitation, str]:
    code = make_invitation_code()
    invitation = Invitation(
        code_digest=keyed_digest(settings, code),
        max_uses=max_uses,
        expires_at=utc_now() + timedelta(days=expires_in_days),
        created_by_user_id=None if created_by is None else created_by.id,
    )
    database_session.add(invitation)
    database_session.flush()
    return invitation, code


def create_session(
    database_session: Session, settings: Settings, user: User
) -> tuple[SessionRecord, str, str]:
    token = make_token()
    csrf_token = make_token()
    now = utc_now()
    session_record = SessionRecord(
        user_id=user.id,
        token_digest=keyed_digest(settings, token),
        csrf_digest=keyed_digest(settings, csrf_token),
        expires_at=expires_after_hours(settings.session_ttl_hours),
        last_seen_at=now,
    )
    database_session.add(session_record)
    database_session.flush()
    return session_record, token, csrf_token


def revoke_session(auth: AuthenticatedSession) -> None:
    auth.session.revoked_at = utc_now()


def rotate_session(
    database_session: Session, settings: Settings, auth: AuthenticatedSession
) -> tuple[SessionRecord, str, str]:
    revoke_session(auth)
    return create_session(database_session, settings, auth.user)


def issue_email_verification_token(
    database_session: Session, settings: Settings, user: User
) -> str:
    database_session.execute(
        update(EmailVerificationToken)
        .where(EmailVerificationToken.user_id == user.id, EmailVerificationToken.used_at.is_(None))
        .values(used_at=utc_now())
    )
    token = make_token()
    database_session.add(
        EmailVerificationToken(
            user_id=user.id,
            token_digest=keyed_digest(settings, token),
            expires_at=expires_after_hours(settings.email_verification_ttl_hours),
        )
    )
    return token


def confirm_email_verification(
    database_session: Session, settings: Settings, token: str
) -> User | None:
    verification = database_session.execute(
        select(EmailVerificationToken)
        .where(
            EmailVerificationToken.token_digest == keyed_digest(settings, token),
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.expires_at > utc_now(),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if verification is None:
        return None
    user = database_session.execute(
        select(User).where(User.id == verification.user_id).with_for_update()
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    verification.used_at = utc_now()
    user.email_verified_at = utc_now()
    return user


def issue_password_reset_token(database_session: Session, settings: Settings, user: User) -> str:
    database_session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=utc_now())
    )
    token = make_token()
    database_session.add(
        PasswordResetToken(
            user_id=user.id,
            token_digest=keyed_digest(settings, token),
            expires_at=utc_now() + timedelta(minutes=settings.password_reset_ttl_minutes),
        )
    )
    return token


def reset_password(
    database_session: Session, settings: Settings, token: str, password_hash: str
) -> bool:
    reset = database_session.execute(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.token_digest == keyed_digest(settings, token),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > utc_now(),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if reset is None:
        return False
    user = database_session.execute(
        select(User).where(User.id == reset.user_id).with_for_update()
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        return False
    now = utc_now()
    reset.used_at = now
    user.password_hash = password_hash
    database_session.execute(
        update(SessionRecord)
        .where(SessionRecord.user_id == user.id, SessionRecord.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    return True
