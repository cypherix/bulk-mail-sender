"""
templating.py
-------------
Loads templates/email_template.txt and renders it per-recipient.

The template's first line must be "SUBJECT: ..." — everything after the
blank line that follows is the email body. Both subject and body support
these placeholders: {first_name}, {name}, {title}, {company},
{sender_name}, {sender_email}.

Keeping the template in a plain .txt file (rather than hardcoded in Python)
means you can tweak the wording without touching code — and re-read it
before every run to review the message you're about to send at scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from excel_reader import Recipient


class TemplateError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    body: str


def load_template(template_path: Path) -> tuple[str, str]:
    """Returns (subject_template, body_template)."""
    text = Path(template_path).read_text(encoding="utf-8")
    if not text.startswith("SUBJECT:"):
        raise TemplateError(
            f"{template_path} must start with a line 'SUBJECT: ...' followed by "
            f"a blank line and then the email body."
        )
    first_line, _, rest = text.partition("\n")
    subject_template = first_line[len("SUBJECT:"):].strip()
    body_template = rest.lstrip("\n")
    if not subject_template or not body_template.strip():
        raise TemplateError(f"{template_path} is missing a subject or body.")
    return subject_template, body_template


def render(
    subject_template: str,
    body_template: str,
    recipient: Recipient,
    sender_name: str,
    sender_email: str,
) -> RenderedEmail:
    fields = {
        "first_name": recipient.first_name,
        "name": recipient.name,
        "title": recipient.title or "your role",
        "company": recipient.company or "your organization",
        "sender_name": sender_name,
        "sender_email": sender_email,
    }
    try:
        subject = subject_template.format(**fields)
        body = body_template.format(**fields)
    except KeyError as e:
        raise TemplateError(f"Unknown placeholder {e} in template.") from e
    return RenderedEmail(subject=subject, body=body)
