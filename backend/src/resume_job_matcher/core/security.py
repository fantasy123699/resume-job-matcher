import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from pwdlib import PasswordHash

from resume_job_matcher.core.config import Settings

PASSWORD_HASHER = PasswordHash.recommended()


def utc_now() -> datetime:
    return datetime.now(UTC)


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return PASSWORD_HASHER.verify(password, password_hash)


def make_token() -> str:
    return secrets.token_urlsafe(32)


def make_invitation_code() -> str:
    return f"rjm_{secrets.token_urlsafe(18)}"


def keyed_digest(settings: Settings, value: str) -> str:
    secret = settings.session_secret.get_secret_value().encode("utf-8")
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()


def expires_after_hours(hours: int) -> datetime:
    return utc_now() + timedelta(hours=hours)
