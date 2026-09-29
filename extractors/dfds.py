#!/usr/bin/env python3
"""DFDS ferry booking confirmations.

The confirmation arrives as plain text with one block per crossing:

    BOOKING NUMBER: <digits>
    NO. OF PASSENGERS: <n>
    OUTWARD JOURNEY:
    Route: <from> - <to>
    Date: <Month D, YYYY>
    Time: <HH:MM>

A return booking repeats the block under `RETURN JOURNEY:`, so each
crossing becomes its own `BoatReservation`.

Only the departure is given - DFDS puts the arrival time on the PDF
travel document linked from the mail, not in the body - so the
reservation carries `departureTime` alone.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

BOOKING_RE = re.compile(r"BOOKING NUMBER:\s*(\d+)", re.IGNORECASE)
PASSENGERS_RE = re.compile(r"NO\. OF PASSENGERS:\s*(\d+)", re.IGNORECASE)
LEG_RE = re.compile(
    r"^(OUTWARD|RETURN)\s+JOURNEY:\s*$",
    re.IGNORECASE | re.MULTILINE,
)
ROUTE_RE = re.compile(r"^Route:\s*(.+?)\s+-\s+(.+?)\s*$", re.MULTILINE)
DATE_RE = re.compile(r"^Date:\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\s*$", re.MULTILINE)
TIME_RE = re.compile(r"^Time:\s*(\d{1,2}):(\d{2})\s*$", re.MULTILINE)


def parse_leg(window: str) -> dict | None:
    route = ROUTE_RE.search(window)
    date = DATE_RE.search(window)
    time = TIME_RE.search(window)
    if not route or not date or not time:
        return None

    for fmt in ("%B", "%b"):
        try:
            month = datetime.strptime(date.group(1), fmt).month
        except ValueError:
            continue
        break
    else:
        return None

    try:
        departs = datetime(
            int(date.group(3)),
            month,
            int(date.group(2)),
            int(time.group(1)),
            int(time.group(2)),
        )
    except ValueError:
        return None

    return {
        "origin": route.group(1).strip(),
        "destination": route.group(2).strip(),
        "departs": departs,
    }


def main() -> int:
    mail = read_message()

    text = mail.text or ""
    if not text and mail.html:
        text = strip_html(mail.html, block_tags=True)
    if not text:
        return 0

    booking = BOOKING_RE.search(text)
    if not booking:
        return 0
    reference = booking.group(1)

    headings = list(LEG_RE.finditer(text))
    if not headings:
        return 0

    legs = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        leg = parse_leg(text[heading.end() : end])
        if leg is not None:
            leg["direction"] = heading.group(1).lower()
            legs.append(leg)
    if not legs:
        return 0

    passengers = PASSENGERS_RE.search(text)

    # Direction (outward/return) goes into `reservationNumber` so both
    # crossings of a return booking survive as separate calendar events;
    # a bare booking number would collide because downstream sinks key
    # off the reservation number. Delays keep the direction intact, so a
    # rescheduled crossing still updates the same event.
    multi_leg = len(legs) > 1
    for leg in legs:
        direction = leg["direction"]
        number = f"{reference}-{direction}" if multi_leg else reference
        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "BoatReservation",
            "reservationNumber": number,
            "reservationFor": {
                "@type": "BoatTrip",
                "provider": {"@type": "Organization", "name": "DFDS"},
                "departureBoatTerminal": {
                    "@type": "BoatTerminal",
                    "name": leg["origin"],
                },
                "arrivalBoatTerminal": {
                    "@type": "BoatTerminal",
                    "name": leg["destination"],
                },
                "departureTime": leg["departs"].strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        if passengers:
            reservation["numSeats"] = int(passengers.group(1))

        suffix = f"-{direction}" if multi_leg else ""
        Path(f"dfds-{reference}{suffix}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
