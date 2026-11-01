#!/usr/bin/env python3
"""Aer Lingus booking confirmations.

Once the tags are stripped, the 2011 template lists each flight as:

    Flight
    EI0712 - Tue 15 Feb 2039
    Departs:
    Copenhagen (CPH) 15:10
    Arrives:
    Cork-Terminal 1 (ORK) 15:50
    Status:
    W/Economy Class CONFIRMED

The booking reference follows "Booking Reference:", the passenger names
"Passenger(s)", and the ticket number "Ticket Numbers" / "Issue Date".
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

FLIGHT_RE = re.compile(r"^([A-Z0-9]{2})0*(\d{1,4}) - \w{3} (\d{1,2} \w{3} \d{4})$")
PLACE_RE = re.compile(r"^(.+?)(?:-Terminal (\S+))? \(([A-Z]{3})\) (\d{2}:\d{2})$")
STATUS_RE = re.compile(r"^([A-Z])/(.+?) Class (\w+)$")
TICKET_RE = re.compile(r"^\d{13}$")
TITLE_RE = re.compile(r"^(?:MR|MRS|MS|MISS|MSTR|DR) ")
CONTEXT = {
    "@vocab": "https://schema.org/",
    "pending": "https://pending.schema.org/",
}


def airport(m: re.Match) -> dict:
    return {"@type": "Airport", "name": m.group(1), "iataCode": m.group(3)}


def after(lines: list[str], label: str, start: int = 0) -> str:
    try:
        return lines[lines.index(label, start) + 1]
    except (ValueError, IndexError):
        raise ValueError(f"no line after {label!r}") from None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]
    reference = after(lines, "Booking Reference:")
    passengers = []
    i = lines.index("Passenger(s)") + 1
    while i < len(lines) and TITLE_RE.match(lines[i]):
        passengers.append(TITLE_RE.sub("", lines[i]).title())
        i += 1
    ticket = None
    if "Ticket Numbers" in lines:
        ticket = next(
            (
                line
                for line in lines[lines.index("Ticket Numbers") :]
                if TICKET_RE.match(line)
            ),
            None,
        )

    starts = [i for i, line in enumerate(lines) if line == "Flight"]
    if not starts:
        raise ValueError(f"booking {reference} lists no flights")
    for start in starts:
        flight = FLIGHT_RE.match(lines[start + 1])
        if not flight:
            raise ValueError(f"unrecognised flight line {lines[start + 1]!r}")
        departs = PLACE_RE.match(after(lines, "Departs:", start))
        arrives = PLACE_RE.match(after(lines, "Arrives:", start))
        if not departs or not arrives:
            raise ValueError(f"unrecognised airports for {lines[start + 1]!r}")
        day = datetime.strptime(flight.group(3), "%d %b %Y")
        departure = datetime.combine(
            day, datetime.strptime(departs.group(4), "%H:%M").time()
        )
        arrival = datetime.combine(
            day, datetime.strptime(arrives.group(4), "%H:%M").time()
        )
        if arrival < departure:
            arrival += timedelta(days=1)

        segment: dict = {
            "@type": "Flight",
            "flightNumber": flight.group(2),
            "airline": {"@type": "Airline", "iataCode": flight.group(1)},
            "departureAirport": airport(departs),
            "arrivalAirport": airport(arrives),
            "departureTime": departure.strftime("%Y-%m-%dT%H:%M:%S"),
            "arrivalTime": arrival.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if departs.group(2):
            segment["departureTerminal"] = departs.group(2)
        if arrives.group(2):
            segment["arrivalTerminal"] = arrives.group(2)
        segment["airline"]["name"] = after(lines, "Airline:", start)

        reservation: dict = {
            "@context": CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": reference,
            "reservationFor": segment,
        }
        status = STATUS_RE.match(after(lines, "Status:", start))
        if status:
            if status.group(3) == "CONFIRMED":
                reservation["reservationStatus"] = (
                    "https://schema.org/ReservationConfirmed"
                )
            reservation["reservationFor"]["pending:cabinClass"] = status.group(2)
            reservation["reservationFor"]["pending:bookingClass"] = status.group(1)
        if len(passengers) == 1:
            reservation["underName"] = {"@type": "Person", "name": passengers[0]}
        if ticket:
            reservation["ticketNumber"] = ticket

        number = flight.group(1) + flight.group(2)
        stamp = departure.strftime("%Y%m%d")
        Path(f"aer-lingus-{reference}-{stamp}-{number}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
