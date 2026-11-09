#!/usr/bin/env python3
"""British Airways boarding passes, mailed from `ba@ba.com` after online
check-in.

The mail says nothing but that the boarding pass is attached; the
details are in the PDF, as columns of labels with values beneath:

    Flight      From      To         Group   Seat
    BA0001      ALPHA     BETA       4       1A
    Date                             Boarding At   Departure time
    4  March                         07:05         07:45
    Operating Airline   Class            Booking reference   Frequent flyer
    British Airways     Euro Traveller   ZZZZZZ              BA/

The date has no year. The flight itself comes from the e-ticket receipt
the `british-airways` extractor reads, so this one writes no
reservation: each PDF is filed as its flight's ticket, with a
`.ticket.json` naming the booking reference and day.
"""

from __future__ import annotations

import io
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import boarding_day, read_message

FLIGHT_RE = re.compile(r"^[A-Z0-9]{2}\d{1,4}$")
DATE_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)")
BOOKING_RE = re.compile(r"^[A-Z0-9]{6}$")


def below(lines: list[str], label: str) -> str | None:
    """The value under `label`: the words on the next non-blank line
    nearest the column the label starts in. Words up to two spaces apart
    are one value (`18  September`); columns are further apart."""
    for i, line in enumerate(lines):
        column = line.find(label)
        if column < 0:
            continue
        for value_line in lines[i + 1 :]:
            if value_line.strip():
                words = [
                    (m.start(), m.group())
                    for m in re.finditer(r"\S+(?: {1,2}\S+)*", value_line)
                ]
                if not words:
                    return None
                return min(words, key=lambda w: abs(w[0] - column))[1]
        return None
    return None


def main() -> int:
    mail = read_message()
    mail_date = mail.date or datetime.now(UTC)
    pdfs = [a for a in mail.attachments if a.looks_like_pdf()]
    if not pdfs:
        raise ValueError("no boarding pass attached")
    for pdf in pdfs:
        page = PdfReader(io.BytesIO(pdf.bytes)).pages[0]
        lines = page.extract_text(extraction_mode="layout").splitlines()
        flight = below(lines, "Flight")
        booking = below(lines, "Booking reference")
        day = below(lines, "Date")
        day_match = DATE_RE.match(day or "")
        if not (
            flight
            and FLIGHT_RE.match(flight)
            and booking
            and BOOKING_RE.match(booking)
            and day_match
        ):
            raise ValueError(
                f"{pdf.filename}: unrecognised boarding pass "
                f"(flight {flight!r}, booking {booking!r}, date {day!r})"
            )
        when = boarding_day(int(day_match.group(1)), day_match.group(2), mail_date)
        slug = f"ba-{flight.lower()}-{when}"
        Path(f"{slug}.ticket.pdf").write_bytes(pdf.bytes)
        record = {
            "reservationNumber": booking,
            "provider": "British Airways",
            "date": when.isoformat(),
        }
        Path(f"{slug}.ticket.json").write_text(json.dumps(record))
    return 0


if __name__ == "__main__":
    sys.exit(main())
