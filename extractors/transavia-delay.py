#!/usr/bin/env python3
"""Transavia flight-delay notifications (TIP@transavia.com).

These mails carry no machine-readable booking data - only a single
human-facing paragraph that always reads:

    Your booking: DDDDDD
    ...
    your flight HV5314 from <origin> to <destination> on DD/MM/YYYY has
    been delayed ... The new departure time is HH:MM local time.

The subject and body together give us the booking code, flight number,
origin/destination, date, and new departure time. We re-emit a
`FlightReservation` with the *new* departureTime keyed on the same
`reservationNumber` so the existing calendar event (originally fed by
TripIt or schema-ld) gets updated by UID match.

The original booking confirmation comes via a TripIt forward and is
processed through the unforward path. This extractor only handles the
delay update; the initial booking is not reconstructed here.
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


BOOKING_RE = re.compile(r"Your booking:\s*([A-Z0-9]{5,8})")
FLIGHT_RE = re.compile(
    r"flight\s+([A-Z]{2}\d{1,4})\s+from\s+(.+?)\s+to\s+(.+?)\s+on\s+"
    r"(\d{1,2}/\d{1,2}/\d{4})\s+has\s+been\s+delayed",
    re.I,
)
NEW_TIME_RE = re.compile(r"new\s+departure\s+time\s+is\s+(\d{1,2}:\d{2})", re.I)
AIRPORT_NAME_RE = re.compile(r"^(.*?)\s*\(([^)]+)\)\s*$")


def strip_html(body: str) -> str:
    text = re.sub(r"<[^>]+>", " ", body)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def airport_from_phrase(phrase: str) -> dict:
    """Turn "Cyprus (Larnaca)" or "Amsterdam (Schiphol)" into a
    schema.org Airport object.

    Transavia's TIP template writes the *city* outside the parens and
    the *airport name* inside. We use the airport name as the schema
    `name` and keep the country/city as `address` so downstream tooling
    still has something to show. The IATA code isn't in the body, so we
    leave it unset.
    """
    m = AIRPORT_NAME_RE.match(phrase.strip())
    if m:
        return {
            "@type": "Airport",
            "name": m.group(2).strip(),
            "address": m.group(1).strip(),
        }
    return {"@type": "Airport", "name": phrase.strip()}


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html)

    booking = BOOKING_RE.search(text)
    flight = FLIGHT_RE.search(text)
    new_time = NEW_TIME_RE.search(text)
    if not (booking and flight and new_time):
        return 0

    booking_code = booking.group(1)
    flight_no = flight.group(1)
    origin_phrase = flight.group(2)
    dest_phrase = flight.group(3)
    date_str = flight.group(4)
    time_str = new_time.group(1)

    try:
        new_dep = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
    except ValueError:
        return 0

    # IATA code for the carrier is constant; flight_no already includes
    # it (e.g. "HV5314").
    iata = flight_no[:2]
    number = flight_no[2:]

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "reservationNumber": booking_code,
        "reservationStatus": "https://schema.org/ReservationConfirmed",
        "modifiedTime": (mail.date.isoformat() if mail.date else None),
        "reservationFor": {
            "@type": "Flight",
            "flightNumber": number,
            "airline": {
                "@type": "Airline",
                "iataCode": iata,
                "name": "Transavia",
            },
            "departureAirport": airport_from_phrase(origin_phrase),
            "arrivalAirport": airport_from_phrase(dest_phrase),
            "departureTime": new_dep.strftime("%Y-%m-%dT%H:%M:%S"),
        },
    }
    # Drop the modifiedTime key if we couldn't determine the date.
    if reservation["modifiedTime"] is None:
        del reservation["modifiedTime"]

    Path(f"transavia-{booking_code}-{flight_no}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
