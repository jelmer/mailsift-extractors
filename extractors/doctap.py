#!/usr/bin/env python3
"""DocTap GP appointment confirmations and reminders.

DocTap (`patients@doctap.co.uk`) sends booking confirmations and
reminders for private GP appointments. The HTML body has a stable
labelled-list shape:

    Appointment: <type / duration>
    When: Thursday July 04, 2024 11:15
    Where: <multi-line address>
    Dr <Name>: <bio paragraph>

We emit a single `EventReservation`. The same UID is used for both
the confirmation and the reminder so the reminder is a no-op update.
Cancellation isn't surfaced in this template; if DocTap adds an
explicit cancel mail later it'll need its own handler.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

APPOINTMENT_RE = re.compile(r"Appointment:\s*\n?\s*(.+?)(?=\n\n|\nWhen:|$)", re.DOTALL)
WHEN_RE = re.compile(
    r"When:\s*\n?\s*"
    r"([A-Z][a-z]+\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2})"
)
WHERE_RE = re.compile(r"Where:?\s*\n?\s*(.+?)(?=\n\n|\nDetails:|\nDr\b|$)", re.DOTALL)
PRACTITIONER_RE = re.compile(r"^(Dr\s+[A-Z][a-zA-Z'\- ]+?)\s*:", re.MULTILINE)


def parse_when(when_str: str) -> datetime | None:
    # "Thursday July 04, 2024 11:15"
    try:
        return datetime.strptime(when_str.strip(), "%A %B %d, %Y %H:%M")
    except ValueError:
        return None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html, block_tags=True)

    appt_match = APPOINTMENT_RE.search(text)
    when_match = WHEN_RE.search(text)
    if not when_match:
        return 0
    appt = appt_match.group(1).strip() if appt_match else "Appointment"

    start = parse_when(when_match.group(1))
    if start is None:
        return 0

    location = None
    where_match = WHERE_RE.search(text)
    if where_match:
        location = re.sub(r"\s*\n\s*", ", ", where_match.group(1).strip())

    practitioner = None
    p_match = PRACTITIONER_RE.search(text)
    if p_match:
        practitioner = p_match.group(1).strip()

    summary_parts = [appt]
    if practitioner:
        summary_parts.append(f"with {practitioner}")
    summary = " ".join(summary_parts)

    # Deterministic UID based on the appointment start so confirmation,
    # reminder, and any later mails with the same time collapse to one
    # calendar event.
    uid_basis = start.strftime("%Y-%m-%dT%H%M")
    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationNumber": f"doctap-{uid_basis}",
        "reservationFor": {
            "@type": "Event",
            "name": summary,
            "startDate": start.strftime("%Y-%m-%dT%H:%M:%S"),
        },
    }
    if location:
        reservation["reservationFor"]["location"] = {
            "@type": "Place",
            "name": location,
        }

    Path(f"doctap-{uid_basis}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
