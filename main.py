#!/usr/bin/env python3
"""
main.py
-------
Orchestrates a resume-outreach run: reads recipients from an Excel sheet,
skips anyone already emailed (persisted across runs), renders a
personalized message per recipient, and sends with a deliberate delay
between each send.

Usage:
    python main.py --excel recipients.xlsx --dry-run
    python main.py --excel recipients.xlsx
    python main.py --excel recipients.xlsx --limit 10 --delay 60

Always run with --dry-run first to review exactly what would be sent.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from config import Config, ConfigError
from excel_reader import ExcelReadError, load_recipients
from email_sender import PermanentSendError, TransientSendError, send_one
from templating import TemplateError, load_template, render
from tracker import SentTracker

DEFAULT_TEMPLATE_PATH = Path(__file__).parent / "templates" / "email_template.txt"


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mail_sender.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Send personalized resume emails from an Excel list.")
    p.add_argument("--excel", required=True, type=Path, help="Path to the .xlsx recipient list.")
    p.add_argument(
        "--template", type=Path, default=DEFAULT_TEMPLATE_PATH,
        help="Path to the email template (.txt). Defaults to templates/email_template.txt",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Render and log every email without sending or contacting SMTP at all.",
    )
    p.add_argument(
        "--limit", type=int, default=None,
        help="Max number of emails to send this run (overrides MAX_EMAILS_PER_RUN if smaller).",
    )
    p.add_argument(
        "--delay", type=int, default=None,
        help="Seconds to wait between sends (overrides RATE_LIMIT_SECONDS).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    try:
        cfg = Config.from_env()
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("See .env.example for the required settings.", file=sys.stderr)
        return 1

    setup_logging(cfg.log_dir)
    logger = logging.getLogger("mail_sender.main")

    run_limit = args.limit if args.limit is not None else cfg.max_emails_per_run
    delay = args.delay if args.delay is not None else cfg.rate_limit_seconds

    try:
        subject_tpl, body_tpl = load_template(args.template)
    except TemplateError as e:
        logger.error("Template error: %s", e)
        return 1

    try:
        recipients, warnings = load_recipients(args.excel)
    except ExcelReadError as e:
        logger.error("Excel read error: %s", e)
        return 1

    for w in warnings:
        logger.warning(w)
    logger.info("Loaded %d valid recipient(s) from %s", len(recipients), args.excel)

    tracker = SentTracker(cfg.sent_log_path)

    to_send = [r for r in recipients if not tracker.already_sent(r.email)]
    skipped_already_sent = len(recipients) - len(to_send)
    if skipped_already_sent:
        logger.info(
            "Skipping %d recipient(s) already emailed in a previous run.",
            skipped_already_sent,
        )

    already_today = tracker.sent_in_last_24h()
    remaining_today = max(0, cfg.max_emails_per_day - already_today)
    if remaining_today == 0:
        logger.warning(
            "Daily cap reached (%d sent in the last 24h, cap=%d). Nothing will be sent.",
            already_today, cfg.max_emails_per_day,
        )
        return 0

    effective_limit = min(run_limit, remaining_today, len(to_send))
    batch = to_send[:effective_limit]

    logger.info(
        "Plan: %d email(s) this run (run_limit=%d, remaining_today=%d, delay=%ds, dry_run=%s)",
        len(batch), run_limit, remaining_today, delay, args.dry_run,
    )

    sent_count = 0
    failed: list[tuple[str, str]] = []

    for i, recipient in enumerate(batch, start=1):
        try:
            rendered = render(subject_tpl, body_tpl, recipient, cfg.sender_name, cfg.sender_email)
        except TemplateError as e:
            logger.error("Skipping %s — template render failed: %s", recipient.email, e)
            failed.append((recipient.email, str(e)))
            continue

        if args.dry_run:
            logger.info(
                "[DRY RUN] Would send to %s | Subject: %s", recipient.email, rendered.subject
            )
            logger.debug("[DRY RUN] Body:\n%s", rendered.body)
            tracker.record(recipient.email, status="dry_run")
            continue

        try:
            send_one(cfg, recipient, rendered)
            tracker.record(recipient.email, status="sent")
            sent_count += 1
        except PermanentSendError as e:
            logger.error("Permanent failure for %s: %s", recipient.email, e)
            failed.append((recipient.email, str(e)))
        except TransientSendError as e:
            logger.error("Gave up on %s after retries: %s", recipient.email, e)
            failed.append((recipient.email, str(e)))

        # Deliberate pause between sends — the single biggest lever against
        # looking like a spam blast to the receiving mail server.
        if i < len(batch):
            time.sleep(delay)

    logger.info(
        "Run complete. sent=%d, failed=%d, skipped_already_sent=%d, skipped_invalid_rows=%d",
        sent_count, len(failed), skipped_already_sent, len(warnings),
    )
    if failed:
        logger.info("Failed recipients:")
        for email, reason in failed:
            logger.info("  - %s: %s", email, reason)

    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
