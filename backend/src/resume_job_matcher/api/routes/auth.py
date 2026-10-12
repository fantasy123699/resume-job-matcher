from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from resume_job_matcher.api.dependencies import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    AuthenticatedSession,
    get_current_auth,
    require_admin,
    require_csrf,
)
from resume_job_matcher.api.schemas import (
    AccountDeletionRequestPayload,
    AccountDeletionResponse,
    InvitationCreateRequest,
    InvitationCreateResponse,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    TokenConfirmRequest,
    UserResponse,
)
from resume_job_matcher.application.account_deletion_service import schedule_account_deletion
from resume_job_matcher.application.auth_service import (
    confirm_email_verification,
    consume_invitation,
    create_invitation,
    create_session,
    enforce_rate_limit,
    issue_email_verification_token,
    issue_password_reset_token,
    reset_password,
    revoke_session,
    rotate_session,
)
from resume_job_matcher.core.config import Settings, get_settings
from resume_job_matcher.core.security import hash_password, verify_password
from resume_job_matcher.infrastructure.db import get_db
from resume_job_matcher.infrastructure.email_sender import (
    EmailDeliveryError,
    send_password_reset_email,
    send_verification_email,
)
from resume_job_matcher.infrastructure.models import User

router = APIRouter(prefix="/api/v1", tags=["auth"])


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        role=cast(Literal["user", "admin"], user.role),
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at,
    )


def client_subject(request: Request, email: str) -> str:
    client_host = "unknown" if request.client is None else request.client.host
    return f"{client_host}:{email}"


def set_session_cookies(
    response: Response, settings: Settings, session_token: str, csrf_token: str
) -> None:
    max_age = settings.session_ttl_hours * 60 * 60
    secure = settings.app_env != "local"
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    secure = settings.app_env != "local"
    response.delete_cookie(key=SESSION_COOKIE, secure=secure, samesite="lax", path="/")
    response.delete_cookie(key=CSRF_COOKIE, secure=secure, samesite="lax", path="/")


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    enforce_rate_limit(
        database_session, settings, "register", client_subject(request, payload.email)
    )
    database_session.commit()
    try:
        consume_invitation(database_session, settings, payload.invitation_code)
        existing_user = database_session.execute(
            select(User).where(User.email == payload.email)
        ).scalar_one_or_none()
        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
            )
        user = User(email=payload.email, password_hash=hash_password(payload.password))
        database_session.add(user)
        database_session.flush()
        _, session_token, csrf_token = create_session(database_session, settings, user)
        verification_token = issue_email_verification_token(database_session, settings, user)
        database_session.commit()
    except IntegrityError as exc:
        database_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
        ) from exc
    except HTTPException:
        database_session.rollback()
        raise
    set_session_cookies(response, settings, session_token, csrf_token)
    try:
        send_verification_email(settings, user, verification_token)
    except EmailDeliveryError:
        pass
    return user_response(user)


@router.post("/auth/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    enforce_rate_limit(database_session, settings, "login", client_subject(request, payload.email))
    database_session.commit()
    user = database_session.execute(
        select(User).where(User.email == payload.email)
    ).scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    _, session_token, csrf_token = create_session(database_session, settings, user)
    database_session.commit()
    set_session_cookies(response, settings, session_token, csrf_token)
    return user_response(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    revoke_session(auth)
    database_session.commit()
    clear_session_cookies(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/auth/session/refresh", response_model=UserResponse)
def refresh_session(
    response: Response,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    _, session_token, csrf_token = rotate_session(database_session, settings, auth)
    database_session.commit()
    set_session_cookies(response, settings, session_token, csrf_token)
    return user_response(auth.user)


@router.get("/me", response_model=UserResponse)
def read_me(auth: AuthenticatedSession = Depends(get_current_auth)) -> UserResponse:
    return user_response(auth.user)


@router.post("/auth/email-verification/request", status_code=status.HTTP_204_NO_CONTENT)
def request_email_verification(
    request: Request,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    enforce_rate_limit(
        database_session,
        settings,
        "email_verification",
        client_subject(request, auth.user.email),
    )
    if auth.user.email_verified_at is None:
        token = issue_email_verification_token(database_session, settings, auth.user)
        database_session.commit()
        try:
            send_verification_email(settings, auth.user, token)
        except EmailDeliveryError:
            pass
    else:
        database_session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/email-verification/confirm", response_model=UserResponse)
def confirm_email_verification_request(
    payload: TokenConfirmRequest,
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    user = confirm_email_verification(database_session, settings, payload.token)
    if user is None:
        database_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification link is invalid or expired",
        )
    database_session.commit()
    return user_response(user)


@router.post("/auth/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    enforce_rate_limit(
        database_session,
        settings,
        "password_reset",
        client_subject(request, payload.email),
    )
    user = database_session.execute(
        select(User).where(User.email == payload.email, User.is_active.is_(True))
    ).scalar_one_or_none()
    if user is not None:
        token = issue_password_reset_token(database_session, settings, user)
        database_session.commit()
        try:
            send_password_reset_email(settings, user, token)
        except EmailDeliveryError:
            pass
    else:
        database_session.commit()
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/auth/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not reset_password(
        database_session, settings, payload.token, hash_password(payload.password)
    ):
        database_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link is invalid or expired",
        )
    database_session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/account/deletion", response_model=AccountDeletionResponse)
def request_account_deletion(
    payload: AccountDeletionRequestPayload,
    response: Response,
    auth: AuthenticatedSession = Depends(require_csrf),
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AccountDeletionResponse:
    if not verify_password(payload.password, auth.user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    deletion_request = schedule_account_deletion(database_session, auth.user)
    clear_session_cookies(response, settings)
    return AccountDeletionResponse(scheduled_for=deletion_request.scheduled_for)


@router.post(
    "/admin/invitations",
    response_model=InvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_invitation(
    payload: InvitationCreateRequest,
    request: Request,
    auth: AuthenticatedSession = Depends(require_admin),
    database_session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> InvitationCreateResponse:
    enforce_rate_limit(
        database_session, settings, "invitation", client_subject(request, auth.user.email)
    )
    invitation, code = create_invitation(
        database_session,
        settings,
        created_by=auth.user,
        max_uses=payload.max_uses,
        expires_in_days=payload.expires_in_days,
    )
    database_session.commit()
    return InvitationCreateResponse(
        id=invitation.id,
        code=code,
        max_uses=invitation.max_uses,
        expires_at=invitation.expires_at,
    )
