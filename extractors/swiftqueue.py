#!/usr/bin/env python3
"""Swiftqueue appointment confirmations and reminders.

Swiftqueue is an appointment platform used by various UK NHS trusts and
clinics. Mails come from `reservations@swiftqueue.com`
with subject `Swiftqueue Appointment Confirmation for HH:MM on <Day>
the <Nth> of <Month> <Year>` (and a similar `Appointment Reminder`
form). The body has a stable `Appointment Details` block:

    Time:
    Friday 6th of December 2024 at 8:45 AM
    Location:
    <full clinic address>

The first paragraph also names the clinic ("appointment at Example
Community Clinic"). We use the
appointment start time as the basis for a deterministic UID so the
confirmation and matching reminder collapse to one calendar event.
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


TIME_RE = re.compile(
    r"Time:\s*\n+\s*"
    r"([A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)\s+of\s+[A-Z][a-z]+\s+\d{4})"
    r"\s+at\s+(\d{1,2}:\d{2}\s*(?:AM|PM))"
)
LOCATION_RE = re.compile(r"Location:\s*\n+\s*(.+?)(?=\n\n|$)", re.S)
CLINIC_RE = re.compile(r"appointment\s+at\s+(.+?)\s*[.\n]", re.I)


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True
        elif tag in ("br", "tr", "p", "div", "h1", "h2", "h3", "td", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False
        elif tag in ("tr", "p", "div", "h1", "h2", "h3", "td", "li"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(body: str) -> str:
    p = _Strip()
    p.feed(body)
    text = "".join(p.parts)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_when(date_str: str, time_str: str) -> datetime | None:
    # Strip the ordinal suffix ("6th" -> "6") so strptime can parse it.
    cleaned = re.sub(r"(\d{1,2})(?:st|nd|rd|th)", r"\1", date_str)
    try:
        return datetime.strptime(
            f"{cleaned} {time_str.replace(' ', '')}", "%A %d of %B %Y %I:%M%p"
        )
    except ValueError:
        return None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html)

    time_match = TIME_RE.search(text)
    if not time_match:
        return 0
    start = parse_when(time_match.group(1), time_match.group(2))
    if start is None:
        return 0

    location = None
    loc_match = LOCATION_RE.search(text)
    if loc_match:
        location = re.sub(r"\s*\n\s*", " ", loc_match.group(1).strip())

    clinic = None
    c_match = CLINIC_RE.search(text)
    if c_match:
        clinic = c_match.group(1).strip()

    summary_parts = ["Appointment"]
    if clinic:
        summary_parts = [clinic]
    summary = " at ".join(summary_parts) if len(summary_parts) > 1 else summary_parts[0]

    uid_basis = start.strftime("%Y-%m-%dT%H%M")
    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationNumber": f"swiftqueue-{uid_basis}",
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

    Path(f"swiftqueue-{uid_basis}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
