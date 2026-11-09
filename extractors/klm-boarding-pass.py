#!/usr/bin/env python3
"""KLM boarding passes, mailed from `yourboardingpass@klm.com` after
check-in.

The mail lists the flights checked in for as a table, one row each:

    Alpha Airport (AAA)
    Alphaville
    Schiphol (AMS)
    Amsterdam
    3 Jun
    KL 1001
    QQQQQQ

The date has no year, and there are no times: the flights themselves
come from the booking confirmation the `klm` extractor reads, so this
one writes no reservations. Each flight's mobile boarding pass is
attached as `Electronic boarding pass-KL1001-03 Jun.png`, all of them
together as `Boarding passes-03 Jun.pdf`. Each PNG is filed as that
flight's ticket, with a `.ticket.json` naming its booking code and day;
the PDF only when some flight has no PNG, as when the passes had to be
collected at the airport.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import boarding_day, read_message, strip_html

DAY_RE = re.compile(r"^(\d{1,2}) ([A-Za-z]{3,})$")
FLIGHT_RE = re.compile(r"^([A-Z0-9]{2}) ?(\d{1,4})$")
BOOKING_RE = re.compile(r"^[A-Z0-9]{6}$")


def flights(lines: list[str], mail_date: datetime) -> list[tuple[str, date, str]]:
    """(flight number, day, booking code) for each row of the table."""
    out = []
    for i in range(len(lines) - 2):
        day = DAY_RE.match(lines[i])
        flight = FLIGHT_RE.match(lines[i + 1])
        if day and flight and BOOKING_RE.match(lines[i + 2]):
            when = boarding_day(int(day.group(1)), day.group(2), mail_date)
            out.append((flight.group(1) + flight.group(2), when, lines[i + 2]))
    return out


def file_ticket(slug: str, ext: str, body: bytes, booking: str, when: date) -> None:
    Path(f"{slug}.ticket.{ext}").write_bytes(body)
    record = {"reservationNumber": booking, "provider": "KLM", "date": when.isoformat()}
    Path(f"{slug}.ticket.json").write_text(json.dumps(record))


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]
    mail_date = mail.date or datetime.now(UTC)
    rows = flights(lines, mail_date)
    if not rows:
        raise ValueError(f"no flights in {mail.subject!r}")

    unfiled = []
    for number, when, booking in rows:
        png = next(
            (
                a
                for a in mail.attachments
                if (a.filename or "").lower().endswith(".png")
                and f"-{number.lower()}-" in (a.filename or "").lower().replace(" ", "")
            ),
            None,
        )
        if png is None:
            unfiled.append((number, when, booking))
            continue
        file_ticket(f"klm-{number.lower()}-{when}", "png", png.bytes, booking, when)

    if unfiled:
        pdf = mail.find_pdf_attachment()
        if pdf is None:
            raise ValueError(f"no boarding pass for {[n for n, _, _ in unfiled]}")
        number, when, booking = unfiled[0]
        file_ticket(
            f"klm-{booking.lower()}-boarding-passes-{when}",
            "pdf",
            pdf.bytes,
            booking,
            when,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
