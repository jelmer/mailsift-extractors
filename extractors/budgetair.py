#!/usr/bin/env python3
"""BudgetAir.co.uk booking verifications.

The "booking verification" mail is the only one that lists the
flights; the per-passenger "E-Ticket for ..." mails carry them only in
a PDF. After tag-stripping, the flights read:

    Your flight
    Airline number: AAAAAA
    Tuesday 19 March 2044
    Flight number: D81234
    07:10
    Bergen (Flesland)
    01:05:00
    08:15
    Tromso (Langnes)
    Flight number: DY456          (same day: no date line)
    ...
    Book a                        (end of the flights)

followed by "Passenger N", the title, given name and surname lines.
Airports are only named, never coded.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

DATE_RE = re.compile(
    r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) \d{1,2} [A-Z][a-z]+ \d{4}$"
)
FLIGHT_RE = re.compile(r"^Flight number: ([A-Z0-9]{2})(\d{1,4})$")
LOCATOR_RE = re.compile(r"^Airline number: ([A-Z0-9]{6})$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
DURATION_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
PASSENGER_RE = re.compile(r"^Passenger \d+$")


def at(day: datetime, time: str) -> datetime:
    hour, minute = time.split(":")
    return day.replace(hour=int(hour), minute=int(minute))


def parse_flight(day: datetime, lines: list[str]) -> dict:
    """`lines` starts after the "Flight number:" line."""
    departs, origin, duration, arrives, destination = lines[:5]
    if not (
        TIME_RE.match(departs)
        and DURATION_RE.match(duration)
        and TIME_RE.match(arrives)
    ):
        raise ValueError(f"unrecognised flight block {lines[:5]!r}")
    departure = at(day, departs)
    arrival = at(day, arrives)
    if arrival < departure:
        arrival += timedelta(days=1)
    return {
        "departureAirport": {"@type": "Airport", "name": origin},
        "arrivalAirport": {"@type": "Airport", "name": destination},
        "departureTime": departure.strftime("%Y-%m-%dT%H:%M:%S"),
        "arrivalTime": arrival.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def passengers(lines: list[str]) -> list[dict]:
    people = []
    for i, line in enumerate(lines):
        if PASSENGER_RE.match(line) and i + 3 < len(lines):
            given, surname = lines[i + 2], lines[i + 3]
            people.append(
                {"@type": "Person", "name": f"{given.title()} {surname.title()}"}
            )
    return people


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]
    try:
        start = lines.index("Your flight")
    except ValueError:
        return 0
    locator = next(
        (m.group(1) for line in lines[start:] if (m := LOCATOR_RE.match(line))), None
    )
    if locator is None:
        raise ValueError("booking verification without an airline number")
    end = lines.index("Booker details", start)
    people = passengers(lines[end:])

    day: datetime | None = None
    count = 0
    for i in range(start, end):
        line = lines[i]
        if DATE_RE.match(line):
            day = datetime.strptime(line, "%A %d %B %Y")
            continue
        m = FLIGHT_RE.match(line)
        if not m:
            continue
        if day is None:
            raise ValueError(f"flight {line!r} before any date")
        flight: dict = {
            "@type": "Flight",
            "flightNumber": m.group(2),
            "airline": {"@type": "Airline", "iataCode": m.group(1)},
            **parse_flight(day, lines[i + 1 : i + 6]),
        }
        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": locator,
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "broker": {"@type": "Organization", "name": "BudgetAir.co.uk"},
            "reservationFor": flight,
        }
        if people:
            reservation["underName"] = people
        stamp = flight["departureTime"][:10].replace("-", "")
        number = m.group(1) + m.group(2)
        Path(f"budgetair-{locator}-{stamp}-{number}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
        count += 1
    if count == 0:
        raise ValueError(f"booking {locator} lists no flights")
    return 0


if __name__ == "__main__":
    sys.exit(main())
