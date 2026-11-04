#!/usr/bin/env python3
"""Eurostar booking and exchange confirmation emails.

A single mail describes both the outbound and the return leg (when
booked together). With one line per block element, a leg reads:

    Outbound
    Eurostar Standard          (or just "Standard" before 2025)
    Wednesday, 10 June 2026
    London St Pancras Int'l
    Rotterdam Centraal
    18:04
    22:32
    3 hrs 28 mins Direct
    Test User
    Coach 5 - Seat 17

We emit one TrainReservation per direction, numbered
`eurostar-<reference>-<direction>`, so an exchange confirmation for the
same direction overwrites in place. A journey with a change of train
is still one leg here: the mail only gives the times of the journey as
a whole.

These mails don't carry a train number, so the reservation has no
trainNumber field.

Every one of these mails lists the whole booking, including legs
already travelled and legs an exchange left alone, so each leg carries
`mailsift:itineraryComplete`: mailsift then cancels the legs filed
from older mail that it no longer lists, such as the train an exchange
moved the booking off.

Exchange confirmations sent since 2026 list no journeys at all, only a
link to the booking; the ticket mail sent alongside them has the new
trains.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

REFERENCE_RE = re.compile(r"^Booking [Rr]eference:\s*([A-Z0-9]{6})$")
DIRECTIONS = {"Outbound": "outbound", "Return": "return"}
DATE_RE = re.compile(r"^[A-Z][a-z]+day, (\d{1,2}) ([A-Z][a-z]+) (\d{4})$")
TIME_RE = re.compile(r"^(\d{2}):(\d{2})$")
SEAT_RE = re.compile(r"^Coach\s+(?P<coach>\S+)\s*-\s*Seat\s+(?P<seat>\S+)$")
NO_JOURNEYS = "To see your updated journey details, please view your booking online"


def parse_leg(lines: list[str]) -> dict:
    """Parse one leg; `lines` runs from just after its header."""
    fare, date_line, origin, destination, dep, arr = lines[:6]
    date_match = DATE_RE.match(date_line)
    dep_match = TIME_RE.match(dep)
    arr_match = TIME_RE.match(arr)
    if not (date_match and dep_match and arr_match):
        raise ValueError(f"unrecognised leg {lines[:6]!r}")
    day = datetime.strptime(" ".join(date_match.groups()), "%d %B %Y")
    departs = day.replace(hour=int(dep_match[1]), minute=int(dep_match[2]))
    arrives = day.replace(hour=int(arr_match[1]), minute=int(arr_match[2]))
    if arrives < departs:
        arrives += timedelta(days=1)

    leg: dict = {
        "reservationFor": {
            "@type": "TrainTrip",
            "provider": {"@type": "Organization", "name": "Eurostar"},
            "departureStation": {"@type": "TrainStation", "name": origin},
            "arrivalStation": {"@type": "TrainStation", "name": destination},
            "departureTime": departs.strftime("%Y-%m-%dT%H:%M:%S"),
            "arrivalTime": arrives.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    }
    # A booking with several passengers lists a seat for each; the
    # first is enough for the calendar entry.
    for line in lines[6:]:
        if m := SEAT_RE.match(line):
            leg["ticketedSeat"] = {
                "@type": "Seat",
                "seatNumber": m.group("seat"),
                "seatSection": m.group("coach"),
                "seatingType": fare,
            }
            break
    return leg


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]

    reference = next(
        (m.group(1) for line in lines if (m := REFERENCE_RE.match(line))), None
    )
    if reference is None:
        raise ValueError("no booking reference")

    headers = [i for i, line in enumerate(lines) if line in DIRECTIONS]
    if not headers:
        if any(line.startswith(NO_JOURNEYS) for line in lines):
            return 0
        raise ValueError(f"booking {reference} lists no journeys")

    legs: dict[str, dict] = {}
    for start, end in zip(headers, headers[1:] + [len(lines)], strict=True):
        direction = DIRECTIONS[lines[start]]
        if direction in legs:
            raise ValueError(f"booking {reference} has two {direction} journeys")
        legs[direction] = parse_leg(lines[start + 1 : end])

    for direction, leg in legs.items():
        slug = f"eurostar-{reference}-{direction}"
        reservation = {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": slug,
            "mailsift:itineraryComplete": True,
            **leg,
        }
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
