"""
config.py
---------
Centralized configuration, loaded from environment variables (optionally via
a .env file). Keeping every tunable in one place makes the rest of the
codebase easy to audit and test.

Required environment variables:
    SMTP_HOST           e.g. smtp.gmail.com
    SMTP_PORT           e.g. 587
    SMTP_USER           your login / email address
    SMTP_PASSWORD       your password or app-specific password
    SENDER_NAME         display name used in the "From" header
    SENDER_EMAIL        email address used in the "From" header

Optional environment variables (sane defaults shown):
    RESUME_PATH              ./resume.pdf
    RATE_LIMIT_SECONDS       45      (min delay between two sends)
    MAX_EMAILS_PER_RUN       50      (hard cap per script execution)
    MAX_EMAILS_PER_DAY       80      (hard cap per rolling 24h window)
    MAX_RETRIES              3       (per-email SMTP retry attempts)
    RETRY_BACKOFF_SECONDS    5       (base backoff, doubles each retry)
    LOG_DIR                  ./logs
    SENT_LOG_PATH             ./logs/sent_log.json
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv  # optional convenience, not required
    load_dotenv()
except ImportError:
    pass


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"Missing required environment variable: {name}. "
            f"Set it in your shell or in a .env file (see .env.example)."
        )
    return value


def _optional_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"Environment variable {name} must be an integer, got {raw!r}")


@dataclass(frozen=True)
class Config:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    sender_name: str
    sender_email: str

    resume_path: Path = field(default_factory=lambda: Path("./resume.pdf"))
    rate_limit_seconds: int = 45
    max_emails_per_run: int = 50
    max_emails_per_day: int = 80
    max_retries: int = 3
    retry_backoff_seconds: int = 5
    log_dir: Path = field(default_factory=lambda: Path("./logs"))
    sent_log_path: Path = field(default_factory=lambda: Path("./logs/sent_log.json"))

    @classmethod
    def from_env(cls) -> "Config":
        smtp_host = _require("SMTP_HOST")
        smtp_port = _optional_int("SMTP_PORT", 587)
        smtp_user = _require("SMTP_USER")
        smtp_password = _require("SMTP_PASSWORD")
        sender_name = _require("SENDER_NAME")
        sender_email = _require("SENDER_EMAIL")

        resume_path = Path(os.environ.get("RESUME_PATH", "./resume.pdf"))
        log_dir = Path(os.environ.get("LOG_DIR", "./logs"))
        sent_log_path = Path(os.environ.get("SENT_LOG_PATH", str(log_dir / "sent_log.json")))

        cfg = cls(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            sender_name=sender_name,
            sender_email=sender_email,
            resume_path=resume_path,
            rate_limit_seconds=_optional_int("RATE_LIMIT_SECONDS", 45),
            max_emails_per_run=_optional_int("MAX_EMAILS_PER_RUN", 50),
            max_emails_per_day=_optional_int("MAX_EMAILS_PER_DAY", 80),
            max_retries=_optional_int("MAX_RETRIES", 3),
            retry_backoff_seconds=_optional_int("RETRY_BACKOFF_SECONDS", 5),
            log_dir=log_dir,
            sent_log_path=sent_log_path,
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.rate_limit_seconds < 10:
            raise ConfigError(
                "RATE_LIMIT_SECONDS < 10 is too aggressive and risks being flagged as "
                "spam / triggering provider rate limits. Use >= 10."
            )
        if not self.resume_path.exists():
            raise ConfigError(f"Resume file not found at: {self.resume_path}")
        self.log_dir.mkdir(parents=True, exist_ok=True)
