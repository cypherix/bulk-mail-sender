"""
tracker.py
----------
Persists a record of every email actually sent, keyed by recipient email
address. This is the core anti-spam safeguard: re-running the script (e.g.
after it crashes halfway, or because you forgot you already ran it) will
never re-send to someone who already received a message, and a rolling
24-hour counter enforces a daily send cap.

Storage format: a single JSON file, e.g.:
{
  "akanksha.puri@sourcefuse.com": {"sent_at": "2026-09-27T10:15:00+00:00", "status": "sent"}
}
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict


@dataclass
class SentRecord:
    sent_at: str
    status: str  # "sent" | "dry_run"


class SentTracker:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)
        tmp.replace(self.path)  # atomic on POSIX, avoids a half-written log file

    def already_sent(self, email: str) -> bool:
        return email.lower() in self._data and self._data[email.lower()]["status"] == "sent"

    def record(self, email: str, status: str = "sent") -> None:
        self._data[email.lower()] = {
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
        }
        self._save()

    def sent_in_last_24h(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        count = 0
        for record in self._data.values():
            if record.get("status") != "sent":
                continue
            try:
                sent_at = datetime.fromisoformat(record["sent_at"])
            except (KeyError, ValueError):
                continue
            if sent_at >= cutoff:
                count += 1
        return count
