# Resume Outreach Mailer

Sends a personalized resume email to each contact in an Excel sheet —
reliably, without spamming anyone twice, and with a full audit trail.

## Structure

```
mail_sender/
├── main.py            # CLI entry point / orchestrator
├── config.py           # All settings, loaded from environment / .env
├── excel_reader.py      # Reads + validates recipients from .xlsx
├── templating.py       # Loads and renders templates/email_template.txt
├── email_sender.py     # SMTP delivery with retry/backoff
├── tracker.py          # Persisted sent-log: prevents duplicate sends
├── templates/
│   └── email_template.txt
├── requirements.txt
└── .env.example
```

## Setup

```bash
cd mail_sender
python -m venv venv && source venv/bin/activate     # optional but recommended
pip install -r requirements.txt

cp .env.example .env
# edit .env: SMTP credentials, SENDER_NAME/EMAIL, RESUME_PATH
```

Put your resume file where `RESUME_PATH` points (default `./resume.pdf`).

Edit `templates/email_template.txt` to change the subject/body. It supports
`{first_name} {name} {title} {company} {sender_name} {sender_email}`.

Your Excel file needs at least `Name` and `Email` columns (case-insensitive);
`Title` and `Company` are used for personalization if present — this matches
the sheet you described (SNo, Name, Email, Title, Company).

## Usage

**Always dry-run first** — this renders every email and writes it to the log
without touching SMTP at all, so you can review exactly what would go out:

```bash
python main.py --excel recipients.xlsx --dry-run
```

Then send for real:

```bash
python main.py --excel recipients.xlsx
```

Useful overrides:

```bash
# Only send 5 this run, 90s apart
python main.py --excel recipients.xlsx --limit 5 --delay 90
```

## Why this won't spam anyone

- **Sent-log dedup** (`logs/sent_log.json`): every successful send is
  recorded by email address. Re-running the script — intentionally or
  because it crashed halfway — will never re-email someone who already
  got a message.
- **Rate limiting**: a configurable delay (default 45s) between each send,
  so you're not blasting a mail server, which is both more polite and
  reduces the chance of your account getting flagged.
- **Daily cap**: `MAX_EMAILS_PER_DAY` caps sends across a rolling 24h
  window regardless of how many times you run the script.
- **Per-run cap**: `MAX_EMAILS_PER_RUN` / `--limit` bounds any single
  execution, so a bug in your recipient list can't fan out to hundreds of
  people at once.
- **Dry-run mode**: review the exact rendered subject/body for every
  recipient before any network call is made.

## Reliability notes

- Transient SMTP/network errors are retried with exponential backoff
  (`MAX_RETRIES`, `RETRY_BACKOFF_SECONDS`); permanent failures (bad address,
  bad auth) are not retried and are reported at the end of the run.
- Invalid or duplicate rows in the Excel sheet are skipped with a warning
  rather than crashing the whole run.
- Every run is logged to `logs/mail_sender.log` (console + file) with
  timestamps, so you have a full audit trail of what was sent, skipped, or
  failed, and why.
- Config uses a `.tmp` file + atomic rename when writing the sent-log, so a
  crash mid-write can't corrupt your dedup history.

## Gmail-specific note

If using Gmail as SMTP_HOST, you'll need an
[App Password](https://myaccount.google.com/apppasswords) (requires 2FA
enabled on the account) — your normal Gmail password will not work with
SMTP.
