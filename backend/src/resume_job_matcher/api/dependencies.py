import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_job_matcher.core.config import Settings, get_settings
from resume_job_matcher.core.security import keyed_digest
from resume_job_matcher.infrastructure.db import get_db
from resume_job_matcher.infrastructure.models import SessionRecord, User, UserRole

SESSION_COOKIE = "rjm_session"
CSRF_COOKIE = "rjm_csrf"


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    session: SessionRecord


def unauthenticated() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


def get_current_auth(
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedSession:
    if session_token is None:
        raise unauthenticated()

    result = database_session.execute(
        select(SessionRecord, User)
        .join(User, User.id == SessionRecord.user_id)
        .where(SessionRecord.token_digest == keyed_digest(settings, session_token))
    ).one_or_none()
    if result is None:
        raise unauthenticated()

    session_record, user = result
    now = datetime.now(UTC)
    if (
        session_record.revoked_at is not None
        or session_record.expires_at <= now
        or not user.is_active
    ):
        raise unauthenticated()
    return AuthenticatedSession(user=user, session=session_record)


def require_csrf(
    request: Request,
    auth: AuthenticatedSession = Depends(get_current_auth),
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
) -> AuthenticatedSession:
    submitted = request.headers.get("X-CSRF-Token")
    if submitted is None or csrf_cookie is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    if not hmac.compare_digest(submitted, csrf_cookie):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    settings = get_settings()
    if not hmac.compare_digest(keyed_digest(settings, submitted), auth.session.csrf_digest):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    return auth


def require_admin(auth: AuthenticatedSession = Depends(require_csrf)) -> AuthenticatedSession:
    if auth.user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required"
        )
    return auth
