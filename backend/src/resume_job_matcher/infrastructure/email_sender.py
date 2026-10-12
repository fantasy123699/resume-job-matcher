import logging
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote

from resume_job_matcher.core.config import Settings
from resume_job_matcher.infrastructure.models import User

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    pass


def send_verification_email(settings: Settings, user: User, token: str) -> None:
    verification_url = f"{settings.web_origin}/verify-email#token={quote(token, safe='')}"
    _send_email(
        settings,
        user.email,
        "请验证你的履历校准台邮箱",
        "你正在注册履历校准台。请在 24 小时内打开下方链接验证邮箱：\n"
        f"{verification_url}\n\n"
        "若不是你本人操作，请忽略此邮件。",
    )


def send_password_reset_email(settings: Settings, user: User, token: str) -> None:
    reset_url = f"{settings.web_origin}/reset-password#token={quote(token, safe='')}"
    _send_email(
        settings,
        user.email,
        "重设你的履历校准台密码",
        "你请求重设履历校准台密码。请在 30 分钟内打开下方链接继续：\n"
        f"{reset_url}\n\n"
        "若不是你本人操作，请忽略此邮件。",
    )


def _send_email(settings: Settings, recipient: str, subject: str, content: str) -> None:
    if settings.mail_provider == "disabled":
        logger.info("Email delivery is disabled in this environment")
        return
    username = settings.mail_smtp_username
    authorization_code = settings.mail_smtp_authorization_code
    if username is None or authorization_code is None:
        raise EmailDeliveryError("Email configuration is incomplete")

    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(content)

    try:
        with smtplib.SMTP_SSL(
            settings.mail_smtp_host,
            settings.mail_smtp_port,
            timeout=10,
            context=ssl.create_default_context(),
        ) as smtp:
            smtp.login(username, authorization_code.get_secret_value())
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("Email delivery failed: %s", type(exc).__name__)
        raise EmailDeliveryError("Email delivery failed") from exc
