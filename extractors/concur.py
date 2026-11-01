#!/usr/bin/env python3
"""Concur Travel itineraries ("Concur Itinerary: TRIP FROM ...").

After tag-stripping, each flight under "Reservations" reads:

    Wednesday, March 13, 2047
    Flight Paris (CDG) to Toronto, ON (YYZ)
    Air Canada 881
    Operated by: Air Canada               (optional)
    This flight leaves on Mar 13 and arrives on Mar 14.   (optional)
    Departure: 10:15 AM
    ...
    Arrival: 12:30 PM
    ...
    Confirmation: BBBBBB
    Status: Confirmed

Only the airline's name is given, not its code.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

STATUSES = {
    "confirmed": "https://schema.org/ReservationConfirmed",
    "cancelled": "https://schema.org/ReservationCancelled",
}

DAY_RE = re.compile(
    r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), (\w+ \d{2}, \d{4})$"
)
ROUTE_RE = re.compile(r"^Flight .+ \(([A-Z]{3})\) to .+ \(([A-Z]{3})\)$")
AIRLINE_RE = re.compile(r"^(.+?) (\d{1,4})$")
ARRIVES_ON_RE = re.compile(
    r"^This flight leaves on \w+ \d+ and arrives on (\w+) (\d+)\.$"
)
TIME_RE = re.compile(r"^(Departure|Arrival): (\d{1,2}:\d{2} [AP]M)$")


def after(lines: list[str], label: str) -> str:
    try:
        return lines[lines.index(label) + 1]
    except (ValueError, IndexError):
        raise ValueError(f"itinerary without {label!r}") from None


def parse_flight(day: date, block: list[str]) -> tuple[dict, str]:
    """(flight, status) for one flight block."""
    route = ROUTE_RE.match(block[0])
    airline = AIRLINE_RE.match(block[1])
    if not route or not airline:
        raise ValueError(f"unrecognised flight {block[:2]!r}")
    times = {m.group(1): m.group(2) for line in block if (m := TIME_RE.match(line))}
    if set(times) != {"Departure", "Arrival"}:
        raise ValueError(f"flight {block[1]!r} without both times")
    departs = datetime.strptime(f"{day} {times['Departure']}", "%Y-%m-%d %I:%M %p")
    arrival_day = day
    for line in block:
        if m := ARRIVES_ON_RE.match(line):
            arrival_day = datetime.strptime(
                f"{m.group(1)} {m.group(2)} {day.year}", "%b %d %Y"
            ).date()
            if arrival_day < day:
                arrival_day = arrival_day.replace(year=day.year + 1)
    arrives = datetime.strptime(
        f"{arrival_day} {times['Arrival']}", "%Y-%m-%d %I:%M %p"
    )
    status_line = next((x for x in block if x.startswith("Status: ")), None)
    if status_line is None:
        raise ValueError(f"flight {block[1]!r} without a status")
    try:
        status = STATUSES[status_line.removeprefix("Status: ").lower()]
    except KeyError:
        raise ValueError(f"unknown status {status_line!r}") from None
    segment = {
        "@type": "Flight",
        "flightNumber": airline.group(2),
        "airline": {"@type": "Airline", "name": airline.group(1)},
        "departureAirport": {"@type": "Airport", "iataCode": route.group(1)},
        "arrivalAirport": {"@type": "Airport", "iataCode": route.group(2)},
        "departureTime": departs.strftime("%Y-%m-%dT%H:%M:%S"),
        "arrivalTime": arrives.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return segment, status


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]
    locator = after(lines, "Agency Record Locator:")
    passengers = after(lines, "Passengers:")

    # TODO: read hotel and car blocks too; no itinerary seen so far has one.
    starts = [i for i, line in enumerate(lines) if ROUTE_RE.match(line)]
    if not starts:
        raise ValueError(f"itinerary {locator} lists no flights")
    bounds = starts[1:] + [len(lines)]
    for start, end in zip(starts, bounds, strict=True):
        header = next(
            (m for line in reversed(lines[:start]) if (m := DAY_RE.match(line))), None
        )
        if header is None:
            raise ValueError(f"flight {lines[start]!r} before any day header")
        day = datetime.strptime(header.group(1), "%B %d, %Y").date()
        segment, status = parse_flight(day, lines[start:end])
        reservation = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": locator,
            "reservationStatus": status,
            "broker": {"@type": "Organization", "name": "Concur"},
            "reservationFor": segment,
            "underName": {"@type": "Person", "name": passengers},
        }
        stamp = segment["departureTime"][:10].replace("-", "")
        origin = segment["departureAirport"]["iataCode"]
        Path(f"concur-{locator}-{stamp}-{origin}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
