#!/usr/bin/env python3
"""Eurostar "Your Eurostar Ticket" mails, sent from 2017 to 2023.

After tag-stripping, each passenger's journeys read:

    Test User
    Going out
    Alpha International to Gamma Central
    03/09/2051                (or 2051-09-03)
    Test User
    10:04
    14:31
    Train no: 9001            (missing before 2018)
    Coach 2 Seat 11
    Ticket no. 200000001      (the number sometimes on its own line)
    Coming back
    ...

The mail repeats every journey for each passenger. We emit one
TrainReservation per direction, keyed like the `eurostar` extractor's
(`eurostar-<reference>-outbound`), so a later mail about the same
booking overwrites it.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

REFERENCE_RE = re.compile(r"^Booking reference:\s*([A-Z0-9]{6})?$", re.IGNORECASE)
REFERENCE_VALUE_RE = re.compile(r"^[A-Z0-9]{6}$")
DIRECTIONS = {"Going out": "outbound", "Coming back": "return"}
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
TRAIN_RE = re.compile(r"^Train no:\s*(\d+)$")
SEAT_RE = re.compile(r"^Coach (\w+) Seat (\w+)$")
TICKET_RE = re.compile(r"^Ticket no\.\s*(\d+)?$")


@dataclass
class Journey:
    origin: str
    destination: str
    departs: datetime
    arrives: datetime
    train: str | None = None
    tickets: list[dict] = field(default_factory=list)


def parse_day(line: str) -> datetime:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(line, fmt)
        except ValueError:
            pass
    raise ValueError(f"unrecognised date {line!r}")


def at(day: datetime, time: str) -> datetime:
    hour, minute = time.split(":")
    return day.replace(hour=int(hour), minute=int(minute))


def parse_journey(lines: list[str]) -> tuple[Journey, dict]:
    """`lines` runs from the route line to the next direction header."""
    origin, sep, destination = lines[0].partition(" to ")
    if not sep:
        raise ValueError(f"unrecognised route {lines[0]!r}")
    day = parse_day(lines[1])
    passenger = lines[2]
    if not (TIME_RE.match(lines[3]) and TIME_RE.match(lines[4])):
        raise ValueError(f"no times after {lines[:3]!r}")
    departs = at(day, lines[3])
    arrives = at(day, lines[4])
    if arrives < departs:
        arrives += timedelta(days=1)
    journey = Journey(origin, destination, departs, arrives)

    ticket: dict = {
        "@type": "Ticket",
        "underName": {"@type": "Person", "name": passenger},
    }
    for i, line in enumerate(lines[5:], start=5):
        if m := TRAIN_RE.match(line):
            journey.train = m.group(1)
        elif m := SEAT_RE.match(line):
            ticket["ticketedSeat"] = {
                "@type": "Seat",
                "seatSection": m.group(1),
                "seatNumber": m.group(2),
            }
        elif m := TICKET_RE.match(line):
            number = m.group(1) or (lines[i + 1] if i + 1 < len(lines) else None)
            if number:
                ticket["ticketNumber"] = number
            break
    return journey, ticket


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]

    reference = None
    for i, line in enumerate(lines):
        if m := REFERENCE_RE.match(line):
            reference = m.group(1)
            following = lines[i + 1] if i + 1 < len(lines) else ""
            if reference is None and REFERENCE_VALUE_RE.match(following):
                reference = following
            break
    if reference is None:
        return 0

    headers = [i for i, line in enumerate(lines) if line in DIRECTIONS]
    if not headers:
        raise ValueError(f"booking {reference} lists no journeys")
    journeys: dict[str, Journey] = {}
    for start, end in zip(headers, headers[1:] + [len(lines)], strict=True):
        direction = DIRECTIONS[lines[start]]
        journey, ticket = parse_journey(lines[start + 1 : end])
        seen = journeys.setdefault(direction, journey)
        if (seen.origin, seen.destination, seen.departs) != (
            journey.origin,
            journey.destination,
            journey.departs,
        ):
            # TODO: support bookings whose passengers travel on different
            # trains, or journeys with a change; neither has been seen.
            raise ValueError(f"booking {reference} has two {direction} journeys")
        seen.tickets.append(ticket)

    for direction, journey in journeys.items():
        trip: dict = {
            "@type": "TrainTrip",
            "provider": {"@type": "Organization", "name": "Eurostar"},
            "departureStation": {"@type": "TrainStation", "name": journey.origin},
            "arrivalStation": {"@type": "TrainStation", "name": journey.destination},
            "departureTime": journey.departs.strftime("%Y-%m-%dT%H:%M:%S"),
            "arrivalTime": journey.arrives.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if journey.train:
            trip["trainNumber"] = journey.train
        slug = f"eurostar-{reference}-{direction}"
        reservation = {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": slug,
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "reservationFor": trip,
            "underName": [ticket["underName"] for ticket in journey.tickets],
            "reservedTicket": journey.tickets,
        }
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
