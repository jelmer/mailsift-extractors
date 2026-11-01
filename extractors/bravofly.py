#!/usr/bin/env python3
"""Bravofly flight booking confirmations (2015 template).

Sent from `reservation@bravofly.com` with subject "Confirmation of
your flight reservation <origin> - <destination>, ID BOOKING <n>".
The flight schedule table flattens (via `strip_html(block_tags=True)`)
into one block per leg, with an `O`/`R` marker before the first leg
of each direction:

    Reservation Number (PNR) : ABC123 - Use this number to check-in online
    ...
    O
    Sat 25/07/2015
    Lufthansa
    LH 0905
    Economy
    11:30 London Heathrow
    14:05 Frankfurt Int.

Only the departure date is given; an arrival clock time earlier than
the departure one is taken to be the next day. That is wrong for the
rare leg that lands on the previous calendar day (eastbound across the
date line), but the mail carries no time zones to tell.

Airports are named but not coded, so `AIRPORTS` maps Bravofly's
spelling to IATA codes.

This mail is not DKIM-signed, so a message-date cutoff guards the
code path against present-day spoofs.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

# The only template seen is from 2015 and unsigned.
# TODO: add a DKIM-gated variant if a signed mail in this template
# turns up.
_CUTOFF = datetime(2018, 1, 1)

# TODO: extend as more Bravofly airport spellings turn up; unknown
# names are emitted without an `iataCode`.
AIRPORTS = {
    "Frankfurt Int.": "FRA",
    "London Heathrow": "LHR",
    "Tokyo Haneda": "HND",
}

BOOKING_RE = re.compile(r"\(ID Booking\), which for you is:\s*(?P<id>\d+)")
PNR_RE = re.compile(r"^Reservation Number \(PNR\)\s*:\s*(?P<pnr>[A-Z0-9]{5,8})\b")
PASSENGER_RE = re.compile(
    r"^(?:Adult|Child|Infant):\s*(?P<name>.+?)(?:\s+Date of birth\s+.*)?$"
)
TICKET_RE = re.compile(r"^Electronic ticket number \(e-tkt\):\s*(?P<ticket>\d+)$")
DATE_RE = re.compile(r"^[A-Z][a-z]{2} (?P<date>\d{2}/\d{2}/\d{4})$")
FLIGHT_RE = re.compile(r"^(?P<airline>[A-Z0-9]{2}) (?P<number>\d{1,4})$")
TIME_PLACE_RE = re.compile(r"^(?P<time>\d{2}:\d{2}) (?P<place>.+)$")


def _airport(name: str) -> dict:
    airport = {"@type": "Airport", "name": name}
    if iata := AIRPORTS.get(name):
        airport["iataCode"] = iata
    return airport


def _passengers(lines: list[str]) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    for i, line in enumerate(lines):
        if m := PASSENGER_RE.match(line):
            ticket_m = TICKET_RE.match(lines[i + 1]) if i + 1 < len(lines) else None
            out.append(
                (m.group("name"), ticket_m.group("ticket") if ticket_m else None)
            )
    return out


def _legs(lines: list[str]) -> list[tuple[str, dict]]:
    """Return (PNR, Flight) pairs from the flight schedule table."""
    legs: list[tuple[str, dict]] = []
    pnr: str | None = None
    for i, line in enumerate(lines):
        if m := PNR_RE.match(line):
            pnr = m.group("pnr")
            continue
        date_m = DATE_RE.match(line)
        if not date_m:
            continue
        if pnr is None:
            raise ValueError(f"flight leg at line {i} precedes any PNR")
        airline, flight, cabin, dep, arr = lines[i + 1 : i + 6]
        flight_m = FLIGHT_RE.match(flight)
        dep_m = TIME_PLACE_RE.match(dep)
        arr_m = TIME_PLACE_RE.match(arr)
        if not (flight_m and dep_m and arr_m):
            raise ValueError(f"unexpected leg {lines[i : i + 6]!r}")
        day = date_m.group("date")
        dep_dt = datetime.strptime(f"{day} {dep_m.group('time')}", "%d/%m/%Y %H:%M")
        arr_dt = datetime.strptime(f"{day} {arr_m.group('time')}", "%d/%m/%Y %H:%M")
        if arr_dt < dep_dt:
            arr_dt += timedelta(days=1)
        legs.append(
            (
                pnr,
                {
                    "@type": "Flight",
                    "flightNumber": flight_m.group("number").lstrip("0") or "0",
                    "airline": {
                        "@type": "Airline",
                        "iataCode": flight_m.group("airline"),
                        "name": airline,
                    },
                    "departureAirport": _airport(dep_m.group("place")),
                    "arrivalAirport": _airport(arr_m.group("place")),
                    "departureTime": dep_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    "arrivalTime": arr_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    "pending:cabinClass": cabin,
                },
            )
        )
    return legs


def main() -> int:
    mail = read_message()
    if mail.date is not None and mail.date.replace(tzinfo=None) >= _CUTOFF:
        return 0
    if not mail.html:
        return 0

    text = strip_html(mail.html, block_tags=True).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in text.split("\n") if line.strip()]
    booking_m = BOOKING_RE.search("\n".join(lines))
    if not booking_m:
        return 0
    booking = booking_m.group("id")
    passengers = _passengers(lines)

    for pnr, flight in _legs(lines):
        reservation: dict = {
            "@context": {
                "@vocab": "https://schema.org/",
                "pending": "https://pending.schema.org/",
            },
            "@type": "FlightReservation",
            "reservationNumber": pnr,
            "broker": {"@type": "Organization", "name": "Bravofly"},
            "reservationFor": flight,
        }
        if len(passengers) == 1:
            name, ticket = passengers[0]
            reservation["underName"] = {"@type": "Person", "name": name}
            if ticket:
                reservation["ticketNumber"] = ticket
        elif passengers:
            reservation["underName"] = [
                {"@type": "Person", "name": name} for name, _ in passengers
            ]
        code = flight["airline"]["iataCode"]
        number = flight["flightNumber"]
        Path(f"bravofly-{booking}-{code}{number}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
