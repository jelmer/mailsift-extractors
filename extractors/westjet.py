#!/usr/bin/env python3
"""WestJet "Your itinerary and receipt" mails.

Once the tags are stripped, the itinerary reads as label and value
lines, one block per flight:

    Reservation code
    AAAAAA
    WESTJET
    Flight Number
    WS 1234
    Confirmed
    Wednesday, 9 August
    Departure:
    YYC CALGARY AB, CANADA
    9:15AM
    ...
    Arrival:
    LAX LOS ANGELES, CA
    11:58AM

followed further down by one "<name>:" and e-ticket number line pair
per passenger. Dates carry no year, so each is the first such date on
or after the mail date. Only the departure date is given; an arrival
time before the departure time means the next day.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

FLIGHT_RE = re.compile(r"^([A-Z0-9]{2}) ?(\d{1,4})$")
DAY_RE = re.compile(r"^[A-Za-z]+, (\d{1,2}) ([A-Za-z]+)$")
AIRPORT_RE = re.compile(r"^([A-Z]{3}) (.+)$")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})([AP]M)$")
PASSENGER_RE = re.compile(r"^(.+):$")
TICKET_RE = re.compile(r"^\d{13}$")


def after(lines: list[str], label: str, start: int = 0) -> int:
    """Index of the line following `label`, searching from `start`."""
    try:
        return lines.index(label, start) + 1
    except ValueError:
        raise ValueError(f"no {label!r} after line {start}") from None


def on_or_after(day: re.Match, sent: date) -> date:
    when = datetime.strptime(
        f"{day.group(1)} {day.group(2)} {sent.year}", "%d %B %Y"
    ).date()
    if when < sent:
        when = when.replace(year=sent.year + 1)
    return when


def at(day: date, line: str) -> datetime:
    m = TIME_RE.match(line)
    if not m:
        raise ValueError(f"unrecognised time {line!r}")
    hour = int(m.group(1)) % 12 + (12 if m.group(3) == "PM" else 0)
    return datetime.combine(day, datetime.min.time()).replace(
        hour=hour, minute=int(m.group(2))
    )


def airport(line: str) -> dict:
    m = AIRPORT_RE.match(line)
    if not m:
        raise ValueError(f"unrecognised airport {line!r}")
    return {"@type": "Airport", "iataCode": m.group(1), "name": m.group(2)}


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    # The passenger name is split with zero-width spaces in places.
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True)
        .replace("\u200b", "")
        .splitlines()
        if line.strip()
    ]
    if mail.date is None:
        raise ValueError("itinerary without a Date header")
    sent = mail.date.date()
    code = lines[after(lines, "Reservation code")]

    tickets = []
    if "Your eTicket receipt can be found here:" in lines:
        i = after(lines, "Your eTicket receipt can be found here:")
        while i + 1 < len(lines) and TICKET_RE.match(lines[i + 1]):
            name = PASSENGER_RE.match(lines[i])
            if not name:
                raise ValueError(f"unrecognised passenger {lines[i]!r}")
            tickets.append((name.group(1), lines[i + 1]))
            i += 2

    starts = [i + 1 for i, line in enumerate(lines) if line == "Flight Number"]
    if not starts:
        raise ValueError(f"itinerary {code} lists no flights")
    for start in starts:
        flight = FLIGHT_RE.match(lines[start])
        day = DAY_RE.match(lines[start + 2])
        if not flight or not day:
            raise ValueError(f"unrecognised flight {lines[start : start + 3]!r}")
        flown = on_or_after(day, sent)
        departure = after(lines, "Departure:", start)
        arrival = after(lines, "Arrival:", departure)
        departs = at(flown, lines[departure + 1])
        arrives = at(flown, lines[arrival + 1])
        if arrives < departs:
            arrives += timedelta(days=1)

        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": code,
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": flight.group(2),
                "airline": {
                    "@type": "Airline",
                    "iataCode": flight.group(1),
                    "name": "WestJet",
                },
                "departureAirport": airport(lines[departure]),
                "arrivalAirport": airport(lines[arrival]),
                "departureTime": departs.strftime("%Y-%m-%dT%H:%M:%S"),
                "arrivalTime": arrives.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        if len(tickets) == 1:
            passenger, ticket = tickets[0]
            reservation["underName"] = {"@type": "Person", "name": passenger}
            reservation["ticketNumber"] = ticket
        elif tickets:
            reservation["underName"] = [
                {"@type": "Person", "name": passenger} for passenger, _ in tickets
            ]
        designator = flight.group(1) + flight.group(2)
        stamp = departs.strftime("%Y%m%d")
        Path(f"westjet-{code}-{stamp}-{designator}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
