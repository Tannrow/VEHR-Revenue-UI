import logging
import os


logger = logging.getLogger(__name__)


def send_email(*, to_email: str, subject: str, body: str) -> None:
    mode = os.getenv("EMAIL_DELIVERY_MODE", "dev").strip().lower()

    if mode == "dev":
        logger.info(
            "DEV EMAIL -> to=%s subject=%s\n%s",
            to_email,
            subject,
            body,
        )
        return

    # TODO: implement production email provider integration.
    logger.warning(
        "Email delivery mode '%s' is not configured; logging email payload only.\n"
        "to=%s subject=%s\n%s",
        mode,
        to_email,
        subject,
        body,
    )
