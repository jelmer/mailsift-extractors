#!/usr/bin/env python3
"""KLM e-ticket ("Ticket voor uw reis").

Sent from `KLM@klm-info.com` after a booking, in Dutch. This is
the actual e-ticket, richer than the sibling `Uw boekingsbevestiging`
mail from `service-flyingblue.com` (which we deliberately don't handle):
this one carries the ticket number, booking class letter, cabin class,
and each segment's origin/destination IATA codes.

The HTML flattens (via `strip_html(block_tags=True)`) into repeating
segment blocks:

    maandag 21 september 2026 - 17:10
    Londen, Heathrow Airport, LHR
    KL1012 |
    Uitgevoerd door
    Economy Class
    | Boekingsklasse:
    Q
    Selecteer uw stoel
    maandag 21 september 2026 - 19:30
    Amsterdam, Schiphol Airport, AMS

Booking metadata sits earlier in the mail as `Boekingscode:`,
`Ticketnummer:`, `Naam passagier:`.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

# Dutch month names as KLM writes them. Weekday and month are both
# lowercase, single spaces between components.
_DUTCH_MONTHS = {
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

# "maandag 21 september 2026 - 17:10". Weekday is discarded; we only
# need the numeric date and time, and the weekday is redundant.
DATE_TIME_RE = re.compile(
    r"^[a-z]+\s+(?P<day>\d{1,2})\s+(?P<month>[a-z]+)\s+(?P<year>\d{4})\s+-\s+(?P<hh>\d{1,2}):(?P<mm>\d{2})\s*$",
    re.IGNORECASE,
)

# "Londen, Heathrow Airport, LHR". IATA is a strict three-letter
# uppercase suffix; anything else is a false positive (there are city
# lines earlier in the mail without one).
AIRPORT_RE = re.compile(
    r"^(?P<city>[^,]+),\s*(?P<name>[^,]+),\s*(?P<iata>[A-Z]{3})\s*$",
)

# The KL flight number sits on its own line in the KLM template, but
# depending on how the receiving MUA collapses whitespace it may share
# a line with the trailing "Uitgevoerd door" cell. Accept both.
FLIGHT_NUMBER_RE = re.compile(
    r"^(?P<airline>[A-Z]{2})\s*(?P<number>\d{1,4})\s*(?:\|\s*(?:Uitgevoerd door)?\s*)?$",
)

# Boekingscode / Ticketnummer / Naam passagier: label + value on
# separate lines in the KLM template. When the HTML has no newline
# between `</strong>` and the value they collapse onto one line;
# accept both by making the value part optional in the group.
BOOKING_CODE_RE = re.compile(
    r"^Boekingscode:\s*(?P<value>[A-Z0-9]{5,8})?\s*$", re.IGNORECASE
)
TICKET_NUMBER_RE = re.compile(
    r"^Ticketnummer:\s*(?P<value>\d{6,15})?\s*$", re.IGNORECASE
)
PASSENGER_RE = re.compile(r"^Naam passagier:\s*(?P<value>.+?)?\s*$", re.IGNORECASE)

# Cabin line sits between the flight number and the booking-class
# letter. KLM uses "Economy Class", "Business Class", "World Business
# Class", etc.
CABIN_RE = re.compile(r"^(?P<cabin>[A-Za-z][A-Za-z ]+?Class)\s*$")

# The booking-class letter follows a `| Boekingsklasse:` line. A single
# uppercase letter in most fare classes (Q, N, J, Y, ...); a two-letter
# code is possible for some carriers, so we accept 1-2 letters. Value
# is optional to cover MUAs that collapse label + value onto one line.
BOOKING_CLASS_LABEL_RE = re.compile(
    r"^\|?\s*Boekingsklasse:\s*(?P<value>[A-Z]{1,2})?\s*$",
    re.IGNORECASE,
)
BOOKING_CLASS_VALUE_RE = re.compile(r"^[A-Z]{1,2}$")


def parse_dt(day: str, month: str, year: str, hh: str, mm: str) -> datetime | None:
    m = _DUTCH_MONTHS.get(month.lower())
    if m is None:
        return None
    try:
        return datetime(int(year), m, int(day), int(hh), int(mm))
    except ValueError:
        return None


def airport(city: str, name: str, iata: str) -> dict:
    return {
        "@type": "Airport",
        "name": name.strip(),
        "iataCode": iata.strip(),
        "address": city.strip(),
    }


def _clean_lines(text: str) -> list[str]:
    """Split into non-empty stripped lines. The HTML template inserts
    trailing carriage returns on every block; strip them so regexes
    can anchor with `$`.
    """
    out = []
    for raw in text.split("\n"):
        line = raw.replace("\r", "").strip()
        if line:
            out.append(line)
    return out


def _find_booking_info(lines: list[str]) -> tuple[str | None, str | None, str | None]:
    """Read the (Boekingscode, Ticketnummer, Naam passagier) header
    triple that sits near the top of the mail.

    The KLM template puts each label on its own line and the value on
    the next. Some MUAs (or a stripping pass with tighter whitespace
    handling) collapse label + value onto a single line; the label
    regexes capture the inline value when present and fall back to
    reading the next line otherwise.
    """
    booking = ticket = passenger = None
    for i, line in enumerate(lines):
        if m := BOOKING_CODE_RE.match(line):
            booking = m.group("value") or (lines[i + 1] if i + 1 < len(lines) else None)
        elif m := TICKET_NUMBER_RE.match(line):
            ticket = m.group("value") or (lines[i + 1] if i + 1 < len(lines) else None)
        elif m := PASSENGER_RE.match(line):
            passenger = m.group("value") or (
                lines[i + 1] if i + 1 < len(lines) else None
            )
    return booking, ticket, passenger


def _parse_segments(lines: list[str], booking: str) -> list[dict]:
    """Walk `lines` looking for each `KL<number>` line and read the
    surrounding block as one flight segment.

    Relative to the flight-number line, the block is:
    the two preceding lines are the departure date+time and airport,
    the following lines carry the cabin and booking class in either
    order, and the next date+time we hit after those is the arrival
    (with the arrival airport on the line after it).
    """
    segments: list[dict] = []
    seen_flights: set[str] = set()
    n = len(lines)
    for i, line in enumerate(lines):
        fn_match = FLIGHT_NUMBER_RE.match(line)
        if not fn_match:
            continue
        airline_code = fn_match.group("airline")
        flight_num = fn_match.group("number")
        if i < 2:
            continue
        dep_airport_line = lines[i - 1]
        dep_dt_line = lines[i - 2]
        dep_airport_m = AIRPORT_RE.match(dep_airport_line)
        dep_dt_m = DATE_TIME_RE.match(dep_dt_line)
        if not dep_airport_m or not dep_dt_m:
            continue
        dep_dt = parse_dt(**dep_dt_m.groupdict())
        if dep_dt is None:
            continue

        # Cabin + booking class follow. Walk forward until we hit the
        # next date/time line, which is the arrival.
        cabin: str | None = None
        booking_class: str | None = None
        expect_class_value = False
        arr_dt_idx: int | None = None
        for j in range(i + 1, min(n, i + 12)):
            current = lines[j]
            if expect_class_value and BOOKING_CLASS_VALUE_RE.match(current):
                booking_class = current
                expect_class_value = False
                continue
            bc_match = BOOKING_CLASS_LABEL_RE.match(current)
            if bc_match:
                inline = bc_match.group("value")
                if inline:
                    booking_class = inline
                else:
                    expect_class_value = True
                continue
            c_match = CABIN_RE.match(current)
            if c_match and cabin is None:
                cabin = c_match.group("cabin")
                continue
            if DATE_TIME_RE.match(current):
                arr_dt_idx = j
                break
        if arr_dt_idx is None or arr_dt_idx + 1 >= n:
            continue
        arr_dt_m = DATE_TIME_RE.match(lines[arr_dt_idx])
        arr_airport_m = AIRPORT_RE.match(lines[arr_dt_idx + 1])
        if not arr_dt_m or not arr_airport_m:
            continue
        arr_dt = parse_dt(**arr_dt_m.groupdict())
        if arr_dt is None:
            continue

        key = f"{airline_code}{flight_num}"
        if key in seen_flights:
            continue
        seen_flights.add(key)

        airline_name = {"KL": "KLM Royal Dutch Airlines", "AF": "Air France"}.get(
            airline_code, airline_code
        )
        flight: dict = {
            "@type": "Flight",
            "flightNumber": flight_num.lstrip("0") or "0",
            "airline": {
                "@type": "Airline",
                "iataCode": airline_code,
                "name": airline_name,
            },
            "departureAirport": airport(**dep_airport_m.groupdict()),
            "arrivalAirport": airport(**arr_airport_m.groupdict()),
            "departureTime": dep_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "arrivalTime": arr_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if cabin:
            flight["pending:cabinClass"] = cabin
        if booking_class:
            flight["pending:bookingClass"] = booking_class

        context: str | dict
        if cabin or booking_class:
            context = {
                "@vocab": "https://schema.org/",
                "pending": "https://pending.schema.org/",
            }
        else:
            context = "https://schema.org"

        segments.append(
            {
                "@context": context,
                "@type": "FlightReservation",
                "reservationNumber": booking,
                "reservationFor": flight,
            }
        )
    return segments


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html, block_tags=True)
    lines = _clean_lines(text)

    booking, ticket, passenger = _find_booking_info(lines)
    if not booking:
        return 0

    segments = _parse_segments(lines, booking)
    if not segments:
        return 0

    for reservation in segments:
        flight = reservation["reservationFor"]
        airline_code = flight["airline"]["iataCode"]
        flight_num = flight["flightNumber"]
        # A passenger name and ticket number apply to the whole
        # booking, so file them under each segment; downstream sinks
        # dedupe by filename anyway.
        if passenger:
            reservation["underName"] = {"@type": "Person", "name": passenger}
        if ticket:
            reservation["ticketNumber"] = ticket
        Path(f"klm-{booking}-{airline_code}{flight_num}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
