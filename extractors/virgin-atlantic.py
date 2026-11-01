#!/usr/bin/env python3
"""Virgin Atlantic e-tickets.

Once the tags are stripped, the e-ticket lists the booking reference
and issue date as label lines, then a grid with one row per flight:

    Reference:
    AAAAAA
    Issue Date:
    31 July 2044
    ...
    FLIGHT
    DEPART DATE
    DEPART AIRPORT
    DEPART TIME
    ARRIVE AIRPORT
    ARRIVE TIME
    CLASS
    STATUS
    OPERATED BY
    VS127
    26 OCT
    MAN
    21:55
    ATL
    10:45
    V
    Economy
    OK
    VS

Dates carry no year, so each is the first such date on or after the
issue date. Only the departure date is given; an arrival time before
the departure time means the next day.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

HEADER = [
    "FLIGHT",
    "DEPART DATE",
    "DEPART AIRPORT",
    "DEPART TIME",
    "ARRIVE AIRPORT",
    "ARRIVE TIME",
    "CLASS",
    "STATUS",
    "OPERATED BY",
]
# CLASS spans two lines, the booking class and then the cabin.
ROW = len(HEADER) + 1
FLIGHT_RE = re.compile(r"^([A-Z0-9]{2})(\d{1,4})$")
DAY_RE = re.compile(r"^(\d{1,2}) ([A-Z]{3})$")
CODE_RE = re.compile(r"^[A-Z]{3}$")
TIME_RE = re.compile(r"^(\d{2}):(\d{2})$")
TICKET_RE = re.compile(r"^(\d{3}) ?(\d{10})$")
CONTEXT = {
    "@vocab": "https://schema.org/",
    "pending": "https://pending.schema.org/",
}


def after(lines: list[str], label: str) -> str:
    try:
        return lines[lines.index(label) + 1]
    except (ValueError, IndexError):
        raise ValueError(f"no line after {label!r}") from None


def on_or_after(day: re.Match, issued: date) -> date:
    when = datetime.strptime(
        f"{day.group(1)} {day.group(2)} {issued.year}", "%d %b %Y"
    ).date()
    if when < issued:
        when = when.replace(year=issued.year + 1)
    return when


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]
    reference = after(lines, "Reference:")
    issued = datetime.strptime(after(lines, "Issue Date:"), "%d %B %Y").date()
    passenger = after(lines, "Passenger:")

    start = next(
        (i for i in range(len(lines)) if lines[i : i + len(HEADER)] == HEADER),
        None,
    )
    if start is None:
        raise ValueError(f"booking {reference}: no flight grid")
    i = start + len(HEADER)
    flights = []
    while i + ROW <= len(lines) and FLIGHT_RE.match(lines[i]):
        row = lines[i : i + ROW]
        number, origin, destination, booking_class, cabin = (
            row[0],
            row[2],
            row[4],
            row[6],
            row[7],
        )
        day, departs, arrives = (
            DAY_RE.match(row[1]),
            TIME_RE.match(row[3]),
            TIME_RE.match(row[5]),
        )
        if not day or not departs or not arrives:
            raise ValueError(f"booking {reference}: unrecognised row {row!r}")
        if not CODE_RE.match(origin) or not CODE_RE.match(destination):
            raise ValueError(f"booking {reference}: unrecognised airports in {row!r}")
        flights.append(
            (
                number,
                on_or_after(day, issued),
                origin,
                departs,
                destination,
                arrives,
                booking_class,
                cabin,
            )
        )
        i += ROW
    if not flights:
        raise ValueError(f"booking {reference} lists no flights")

    ticket = None
    if "TICKET NUMBERS and ENDORSEMENTS" in lines:
        ticket = next(
            (
                "".join(m.groups())
                for line in lines[lines.index("TICKET NUMBERS and ENDORSEMENTS") :]
                if (m := TICKET_RE.match(line))
            ),
            None,
        )

    for (
        number,
        flown,
        origin,
        departs,
        destination,
        arrives,
        booking_class,
        cabin,
    ) in flights:
        flight = FLIGHT_RE.match(number)
        assert flight is not None
        departure = datetime.combine(flown, datetime.min.time()).replace(
            hour=int(departs.group(1)), minute=int(departs.group(2))
        )
        arrival = datetime.combine(flown, datetime.min.time()).replace(
            hour=int(arrives.group(1)), minute=int(arrives.group(2))
        )
        if arrival < departure:
            arrival += timedelta(days=1)
        reservation: dict = {
            "@context": CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": reference,
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": flight.group(2),
                "airline": {
                    "@type": "Airline",
                    "iataCode": flight.group(1),
                    "name": "Virgin Atlantic",
                },
                "departureAirport": {"@type": "Airport", "iataCode": origin},
                "arrivalAirport": {"@type": "Airport", "iataCode": destination},
                "departureTime": departure.strftime("%Y-%m-%dT%H:%M:%S"),
                "arrivalTime": arrival.strftime("%Y-%m-%dT%H:%M:%S"),
                "pending:cabinClass": cabin,
                "pending:bookingClass": booking_class,
            },
            "underName": {"@type": "Person", "name": passenger_name(passenger)},
        }
        if ticket:
            reservation["ticketNumber"] = ticket
        stamp = departure.strftime("%Y%m%d")
        Path(
            f"virgin-atlantic-{reference}-{stamp}-{number}.reservation.json"
        ).write_text(json.dumps(reservation, ensure_ascii=False), encoding="utf-8")
    return 0


def passenger_name(raw: str) -> str:
    """ "USER/TESTMR" -> "Test User"."""
    surname, _, given = raw.partition("/")
    given = re.sub(r"(?:MRS|MR|MS|MISS|MSTR|DR)$", "", given)
    return f"{given.title()} {surname.title()}".strip()


if __name__ == "__main__":
    sys.exit(main())
