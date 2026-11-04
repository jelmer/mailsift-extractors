#!/usr/bin/env python3
"""Eurostar booking and exchange confirmations, sent from 2013 to 2016.

After tag-stripping, each booking in the mail reads:

    London to Brussels return
    Booking reference AAAAAA
    Departs
    Alpha International at 17:04 on Friday 31st January
    Arrives
    Beta Midi at 20:05 on Friday 31st January
    ...
    Test User (Adult)
    Carriage 3 Seat 33          (or "Carriage 3, Seat 33")
    Departs
    ...

A mail can hold several bookings, one per passenger, each listing the
outbound journey and, for a return, the journey back. The dates have
no year, so the year is the one, around the mail's own, on which the
date falls on the weekday given.

We emit one TrainReservation per direction, numbered like the later
Eurostar mails (`eurostar-<reference>-outbound`). The mails have no
train numbers. Each lists the whole booking as it stands, so each leg
carries `mailsift:itineraryComplete`.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

REFERENCE_RE = re.compile(r"^Booking reference ([A-Z0-9]{6})$")
STOP_RE = re.compile(
    r"^(?P<station>.+) at (?P<hour>\d{1,2}):(?P<minute>\d{2}) on "
    r"(?P<weekday>[A-Z][a-z]+day) (?P<day>\d{1,2})(?:st|nd|rd|th)? "
    r"(?P<month>[A-Z][a-z]+)$"
)
SEAT_RE = re.compile(r"^Carriage (\w+),? Seat (\w+)$")
DIRECTIONS = ("outbound", "return")


def resolve_stop(sent: datetime, line: str) -> tuple[str, datetime]:
    """The station and time of a `<station> at 17:04 on Friday 31st January` line.

    The time is on the date within a year of `sent` that falls on the
    weekday given.
    """
    m = STOP_RE.match(line)
    if m is None:
        raise ValueError(f"unrecognised stop {line!r}")
    candidates = []
    for year in (sent.year - 1, sent.year, sent.year + 1):
        try:
            day = datetime.strptime(f"{m['day']} {m['month']} {year}", "%d %B %Y")
        except ValueError:
            # 29 February outside a leap year.
            continue
        if day.strftime("%A") == m["weekday"]:
            candidates.append(day)
    if len(candidates) != 1:
        raise ValueError(f"can't place {line!r} around {sent:%Y}")
    return m["station"], candidates[0].replace(
        hour=int(m["hour"]), minute=int(m["minute"])
    )


def parse_leg(lines: list[str], sent: datetime) -> dict:
    """`lines` runs from a `Departs` line to the next one."""
    if len(lines) < 4 or lines[2] != "Arrives":
        raise ValueError(f"unrecognised journey {lines[:4]!r}")
    origin, departs = resolve_stop(sent, lines[1])
    destination, arrives = resolve_stop(sent, lines[3])
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
    # Each passenger has a seat; the first is enough for the calendar.
    for line in lines[4:]:
        if m := SEAT_RE.match(line):
            leg["ticketedSeat"] = {
                "@type": "Seat",
                "seatSection": m.group(1),
                "seatNumber": m.group(2),
            }
            break
    return leg


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    if mail.date is None:
        raise ValueError("no Date header to place the journeys' dates in")
    sent = mail.date.replace(tzinfo=None)
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]

    starts = [i for i, line in enumerate(lines) if REFERENCE_RE.match(line)]
    if not starts:
        raise ValueError("no booking reference")
    bookings: dict[str, list[dict]] = {}
    for start, end in zip(starts, starts[1:] + [len(lines)], strict=True):
        reference = lines[start].removeprefix("Booking reference ")
        if reference in bookings:
            raise ValueError(f"booking {reference} is listed twice")
        departs = [i for i in range(start, end) if lines[i] == "Departs"]
        if not 1 <= len(departs) <= len(DIRECTIONS):
            raise ValueError(f"booking {reference} has {len(departs)} journeys")
        bookings[reference] = [
            parse_leg(lines[i:j], sent)
            for i, j in zip(departs, departs[1:] + [end], strict=True)
        ]

    for reference, legs in bookings.items():
        for direction, leg in zip(DIRECTIONS, legs, strict=False):
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
