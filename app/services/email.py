import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage


logger = logging.getLogger(__name__)

DEFAULT_FROM_ADDRESS = "no-reply@behr.local"
SMTP_TIMEOUT_SECONDS = 10
TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
FALSE_ENV_VALUES = {"0", "false", "no", "off"}


class EmailDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class SMTPSettings:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    use_tls: bool


def _env_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_ENV_VALUES


def _load_smtp_settings() -> SMTPSettings | None:
    host = os.getenv("SMTP_HOST", "").strip()
    port_raw = os.getenv("SMTP_PORT", "").strip()
    username = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASS", "").strip()
    from_address = os.getenv("SMTP_FROM", "").strip()
    tls_raw = os.getenv("SMTP_TLS")
    tls_value = tls_raw.strip() if tls_raw is not None else ""

    missing: list[str] = []
    if not host:
        missing.append("SMTP_HOST")
    if not port_raw:
        missing.append("SMTP_PORT")
    if not username:
        missing.append("SMTP_USER")
    if not password:
        missing.append("SMTP_PASS")
    if not from_address:
        missing.append("SMTP_FROM")
    if not tls_value:
        missing.append("SMTP_TLS")

    if missing:
        logger.warning(
            "SMTP is not fully configured; falling back to log-only email. missing=%s",
            ",".join(missing),
        )
        return None

    try:
        port = int(port_raw)
    except ValueError:
        logger.warning(
            "SMTP_PORT is invalid (%s); falling back to log-only email.",
            port_raw,
        )
        return None

    tls_normalized = tls_value.lower()
    if tls_normalized not in TRUE_ENV_VALUES and tls_normalized not in FALSE_ENV_VALUES:
        logger.warning(
            "SMTP_TLS is invalid (%s); expected true/false. Falling back to log-only email.",
            tls_value,
        )
        return None

    return SMTPSettings(
        host=host,
        port=port,
        username=username,
        password=password,
        from_address=from_address or DEFAULT_FROM_ADDRESS,
        use_tls=_env_bool(tls_value, default=True),
    )


def _log_email_payload_fallback(
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None,
) -> None:
    logger.info(
        "EMAIL FALLBACK (not sent via SMTP) -> to=%s subject=%s\ntext:\n%s\nhtml:\n%s",
        to,
        subject,
        body_text,
        body_html or "",
    )


def send_email(
    *,
    to: str,
    subject: str,
    body_html: str | None,
    body_text: str,
) -> bool:
    settings = _load_smtp_settings()
    if settings is None:
        _log_email_payload_fallback(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
        return False

    try:
        message = EmailMessage()
        message["From"] = settings.from_address
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body_text)
        if body_html:
            message.add_alternative(body_html, subtype="html")

        logger.info(
            "Email sending started to=%s subject=%s host=%s port=%s tls=%s",
            to,
            subject,
            settings.host,
            settings.port,
            settings.use_tls,
        )

        if settings.use_tls and settings.port == 465:
            with smtplib.SMTP_SSL(
                settings.host,
                settings.port,
                timeout=SMTP_TIMEOUT_SECONDS,
                context=ssl.create_default_context(),
            ) as smtp:
                logger.info(
                    "SMTP connection succeeded host=%s port=%s tls=%s",
                    settings.host,
                    settings.port,
                    settings.use_tls,
                )
                smtp.ehlo()
                smtp.login(settings.username, settings.password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(
                settings.host,
                settings.port,
                timeout=SMTP_TIMEOUT_SECONDS,
            ) as smtp:
                smtp.ehlo()
                if settings.use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                logger.info(
                    "SMTP connection succeeded host=%s port=%s tls=%s",
                    settings.host,
                    settings.port,
                    settings.use_tls,
                )
                smtp.login(settings.username, settings.password)
                smtp.send_message(message)
    except Exception as exc:
        logger.exception(
            "Email send failed to=%s subject=%s host=%s port=%s error=%s",
            to,
            subject,
            settings.host,
            settings.port,
            str(exc),
        )
        raise EmailDeliveryError(f"SMTP email send failed: {exc}") from exc

    logger.info(
        "Email sent to=%s subject=%s",
        to,
        subject,
    )
    return True
