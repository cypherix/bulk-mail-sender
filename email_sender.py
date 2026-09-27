"""
email_sender.py
----------------
Handles the actual SMTP delivery: builds a MIME message with the resume
attached, connects over STARTTLS, and sends — with retry/backoff on
transient failures. Permanent failures (bad recipient address, auth
failure) are not retried, since retrying those just wastes time and looks
more like spam behavior to the mail server.
"""

from __future__ import annotations

import logging
import mimetypes
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

from config import Config
from excel_reader import Recipient
from templating import RenderedEmail

logger = logging.getLogger("mail_sender.email_sender")


class PermanentSendError(RuntimeError):
    """Recipient/address-level failure — do not retry."""


class TransientSendError(RuntimeError):
    """Network/server-level failure — safe to retry."""


def _build_message(
    cfg: Config, recipient: Recipient, rendered: RenderedEmail
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = rendered.subject
    msg["From"] = f"{cfg.sender_name} <{cfg.sender_email}>"
    msg["To"] = recipient.email
    msg.set_content(rendered.body)

    resume_path = Path(cfg.resume_path)
    mime_type, _ = mimetypes.guess_type(resume_path.name)
    maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
    with resume_path.open("rb") as f:
        msg.add_attachment(
            f.read(), maintype=maintype, subtype=subtype, filename=resume_path.name
        )
    return msg


def send_one(cfg: Config, recipient: Recipient, rendered: RenderedEmail) -> None:
    """
    Sends a single email, retrying transient failures up to cfg.max_retries
    times with exponential backoff. Raises PermanentSendError or
    TransientSendError (after retries exhausted) on failure.
    """
    msg = _build_message(cfg, recipient, rendered)

    last_error: Exception | None = None
    for attempt in range(1, cfg.max_retries + 1):
        try:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(cfg.smtp_user, cfg.smtp_password)
                server.send_message(msg)
            logger.info("Sent to %s (attempt %d)", recipient.email, attempt)
            return
        except smtplib.SMTPRecipientsRefused as e:
            # The server rejected this specific address — retrying won't help.
            raise PermanentSendError(f"Recipient refused: {recipient.email}: {e}") from e
        except smtplib.SMTPAuthenticationError as e:
            raise PermanentSendError(f"SMTP authentication failed: {e}") from e
        except (smtplib.SMTPException, OSError, TimeoutError) as e:
            last_error = e
            wait = cfg.retry_backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                "Transient error sending to %s (attempt %d/%d): %s — retrying in %ds",
                recipient.email, attempt, cfg.max_retries, e, wait,
            )
            time.sleep(wait)

    raise TransientSendError(
        f"Failed to send to {recipient.email} after {cfg.max_retries} attempts: {last_error}"
    )
