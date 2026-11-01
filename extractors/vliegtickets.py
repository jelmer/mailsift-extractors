#!/usr/bin/env python3
"""Vliegtickets.nl e-tickets.

The "Uw elektronische tickets" mail lists each segment as label and
value lines once the tags are stripped:

    Vrijdag 22 Oktober 2038
    AIR
    Lufthansa - Vlucht LH 422
    ...
    Van
    Frankfurt International Airport
    Airline locator
    BBBBBB
    Germany
    Stoel
    48-L                      (missing when no seat was assigned)
    10:40 Terminal:2
    ...
    Aankomst
    Boston Logan Int'l Airport
    ...
    Tussenlanding
    0
    12:50 Terminal:E          ("Volgende dag" when it lands the next day)

The airline name before " - Vlucht" is sometimes empty. Airports are
only named, never coded.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

MONTHS = {
    "januari": 1,
    "februari": 2,
    "maart": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "augustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}

DATE_RE = re.compile(
    r"^(?:maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag) (\d{1,2}) (\w+) (\d{4})$",
    re.IGNORECASE,
)
FLIGHT_RE = re.compile(r"^(.*?)\s*- Vlucht ([A-Z0-9]{2}) ?(\d{1,4})$")
TIME_RE = re.compile(r"^(\d{2}):(\d{2})(?: Terminal:(\S+))?( Volgende dag)?$")
CODE_RE = re.compile(r"^Reserveringscode: ([A-Z0-9]{6})$")
PASSENGER_RE = re.compile(
    r"^Passagier: ([A-Z' -]+)/([A-Z' -]+?)(?:\.?(?:MR|MRS|MS|MISS))?$"
)
TICKET_RE = re.compile(r"^\d{13}(?:-\d{3})?$")


def parse_date(line: str) -> date | None:
    m = DATE_RE.match(line)
    if not m:
        return None
    month = MONTHS.get(m.group(2).lower())
    if month is None:
        raise ValueError(f"unknown month in {line!r}")
    return date(int(m.group(3)), month, int(m.group(1)))


def value_after(lines: list[str], label: str) -> int:
    """Index of the line following `label`."""
    try:
        return lines.index(label) + 1
    except ValueError:
        raise ValueError(f"segment without {label!r}") from None


def first_time(lines: list[str], start: int) -> tuple[re.Match, int]:
    for i in range(start, len(lines)):
        m = TIME_RE.match(lines[i])
        if m:
            return m, i
    raise ValueError(f"no time after line {start}")


def parse_segment(day: date, lines: list[str]) -> dict:
    """`lines` runs from the "AIR" line to the next segment."""
    flight = FLIGHT_RE.match(lines[1])
    if not flight:
        raise ValueError(f"unrecognised flight line {lines[1]!r}")

    van = value_after(lines, "Van")
    departure, i = first_time(lines, van)
    aankomst = value_after(lines, "Aankomst")
    if aankomst < i:
        raise ValueError("arrival listed before the departure time")
    arrival, _ = first_time(lines, value_after(lines, "Tussenlanding") + 1)

    departs = datetime.combine(day, datetime.min.time()).replace(
        hour=int(departure.group(1)), minute=int(departure.group(2))
    )
    arrives = datetime.combine(day, datetime.min.time()).replace(
        hour=int(arrival.group(1)), minute=int(arrival.group(2))
    )
    if arrival.group(4):
        arrives += timedelta(days=1)

    segment: dict = {
        "@type": "Flight",
        "flightNumber": flight.group(3),
        "airline": {"@type": "Airline", "iataCode": flight.group(2)},
        "departureAirport": {"@type": "Airport", "name": lines[van]},
        "arrivalAirport": {"@type": "Airport", "name": lines[aankomst]},
        "departureTime": departs.strftime("%Y-%m-%dT%H:%M:%S"),
        "arrivalTime": arrives.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if flight.group(1):
        segment["airline"]["name"] = flight.group(1)
    if departure.group(3):
        segment["departureTerminal"] = departure.group(3)
    if arrival.group(3):
        segment["arrivalTerminal"] = arrival.group(3)
    locator = lines[value_after(lines, "Airline locator")]
    stoel = value_after(lines, "Stoel")
    seat = lines[stoel] if stoel != i else None
    return {"flight": segment, "locator": locator, "seat": seat}


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]

    code = next((m.group(1) for line in lines if (m := CODE_RE.match(line))), None)
    if code is None:
        return 0
    passenger = next((m for line in lines if (m := PASSENGER_RE.match(line))), None)
    ticket = next((line for line in lines if TICKET_RE.match(line)), None)

    starts = [
        (i, day)
        for i, line in enumerate(lines)
        if i + 1 < len(lines) and lines[i + 1] == "AIR" and (day := parse_date(line))
    ]
    if not starts:
        raise ValueError(f"booking {code} lists no flights")
    end_of_segments = lines.index("Ticketing Informatie")
    bounds = [i for i, _ in starts[1:]] + [end_of_segments]

    for (start, day), end in zip(starts, bounds, strict=True):
        segment = parse_segment(day, lines[start + 1 : end])
        flight = segment["flight"]
        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": segment["locator"],
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "broker": {"@type": "Organization", "name": "Vliegtickets.nl"},
            "reservationFor": flight,
        }
        if passenger:
            surname = passenger.group(1).strip().title()
            given = passenger.group(2).strip().title()
            reservation["underName"] = {"@type": "Person", "name": f"{given} {surname}"}
        if ticket:
            reservation["ticketNumber"] = ticket
        if segment["seat"]:
            reservation["ticketedSeat"] = {
                "@type": "Seat",
                "seatNumber": segment["seat"],
            }

        number = flight["airline"]["iataCode"] + flight["flightNumber"]
        stamp = flight["departureTime"][:10].replace("-", "")
        Path(f"vliegtickets-{code}-{stamp}-{number}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
