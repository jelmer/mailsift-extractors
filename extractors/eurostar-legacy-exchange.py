#!/usr/bin/env python3
"""Eurostar exchange confirmations, sent from 2019 to 2023.

After tag-stripping, each journey of the booking reads:

    Going out
    Alpha International to Gamma Central Fri, 29 December
    17:28
    3 hrs 32 mins
    Direct
    20:00
    Test User
    Coach 11, seat 43
    Coming back
    ...

The date has no year, and the mail lists journeys already travelled
too, so the year is the one, around the mail's own, on which the date
falls on the weekday given.

The mail lists the whole booking, including the journey the exchange
left alone, but no train numbers. We emit one TrainReservation per
direction, numbered like the `eurostar-legacy` ticket mails
(`eurostar-<reference>-outbound`), with `mailsift:itineraryComplete`
so that mailsift cancels the trains the booking was moved off.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

REFERENCE_RE = re.compile(r"^Booking reference:\s*([A-Z0-9]{6})$")
DIRECTIONS = {"Going out": "outbound", "Coming back": "return"}
# Older mails leave no space between the destination and the date.
ROUTE_RE = re.compile(
    r"^(?P<origin>.+?) to (?P<destination>.+?)\s*"
    r"(?P<weekday>Mon|Tue|Wed|Thu|Fri|Sat|Sun), (?P<day>\d{1,2}) (?P<month>[A-Z][a-z]+)$"
)
TIME_RE = re.compile(r"^(\d{2}):(\d{2})$")
SEAT_RE = re.compile(r"^Coach (\w+), seat (\w+)$")


def resolve_day(sent: datetime, weekday: str, day: int, month: str) -> datetime:
    """The date within a year of `sent` that falls on `weekday`."""
    candidates = []
    for year in (sent.year - 1, sent.year, sent.year + 1):
        try:
            candidate = datetime.strptime(f"{day} {month} {year}", "%d %B %Y")
        except ValueError:
            # 29 February outside a leap year.
            continue
        if candidate.strftime("%a") == weekday:
            candidates.append(candidate)
    if len(candidates) != 1:
        raise ValueError(f"can't place {weekday}, {day} {month} around {sent:%Y}")
    return candidates[0]


def parse_journey(lines: list[str], sent: datetime) -> dict:
    """`lines` runs from the route line to the next direction header."""
    route = ROUTE_RE.match(lines[0])
    if route is None:
        raise ValueError(f"unrecognised route {lines[0]!r}")
    day = resolve_day(sent, route["weekday"], int(route["day"]), route["month"])
    times = [m for line in lines[1:] if (m := TIME_RE.match(line))]
    if len(times) < 2:
        raise ValueError(f"no departure and arrival time after {lines[0]!r}")
    departs = day.replace(hour=int(times[0][1]), minute=int(times[0][2]))
    arrives = day.replace(hour=int(times[1][1]), minute=int(times[1][2]))
    if arrives < departs:
        arrives += timedelta(days=1)

    leg: dict = {
        "reservationFor": {
            "@type": "TrainTrip",
            "provider": {"@type": "Organization", "name": "Eurostar"},
            "departureStation": {"@type": "TrainStation", "name": route["origin"]},
            "arrivalStation": {
                "@type": "TrainStation",
                "name": route["destination"],
            },
            "departureTime": departs.strftime("%Y-%m-%dT%H:%M:%S"),
            "arrivalTime": arrives.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    }
    # Each passenger has a seat; the first is enough for the calendar.
    for line in lines[1:]:
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
        raise ValueError(f"booking {reference} lists no journeys")
    sent = mail.date.replace(tzinfo=None)
    legs: dict[str, dict] = {}
    for start, end in zip(headers, headers[1:] + [len(lines)], strict=True):
        direction = DIRECTIONS[lines[start]]
        if direction in legs:
            raise ValueError(f"booking {reference} has two {direction} journeys")
        legs[direction] = parse_journey(lines[start + 1 : end], sent)

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
