#!/usr/bin/env python3
"""Transavia booking confirmation (booking@e.transavia.com).

Dutch template. The itinerary block has a fixed shape per leg:

    <weekday-nl> <day> <month-nl> <year>
    HH:MM
    HH:MM
    <origin city> (<origin airport name>)
    <destination city> (<destination airport name>)
    <ORIG_IATA>
    <DEST_IATA>
    Vluchtnummer: HV<digits>

The booking reference is on a "Boekingsnummer: <code>" line (and also
in the Subject). We emit one FlightReservation per leg, keyed on the
booking code + flight number so a later delay update from
transavia-delay.py collapses onto the same event by UID.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

BOOKING_RE = re.compile(r"Boekingsnummer:\s*([A-Z0-9]{5,8})")

# Dutch month names; the mail is always Dutch.
_MONTHS = {
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
_WEEKDAY = r"(?:maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag)"
_MONTH = r"(?:" + "|".join(_MONTHS) + r")"

# Airport clause: city name (may be multi-word) followed by
# "(airport name)". Names allow letters, spaces, dots, apostrophes,
# hyphens; the parenthesised part allows the same plus digits.
_AIRPORT = r"[A-Za-z][A-Za-z .'\-]*?\s*\([^)]+\)"

LEG_RE = re.compile(
    rf"{_WEEKDAY}\s+(\d{{1,2}})\s+({_MONTH})\s+(\d{{4}})\s+"
    r"(\d{1,2}:\d{2})\s+(\d{1,2}:\d{2})\s+"
    rf"({_AIRPORT})\s+({_AIRPORT})\s+"
    r"([A-Z]{3})\s+([A-Z]{3})\s+"
    r"Vluchtnummer:\s*([A-Z]{2})(\d{1,4})",
    re.IGNORECASE,
)


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(html: str) -> str:
    p = _Strip()
    p.feed(html)
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()


def airport_from_phrase(phrase: str) -> dict:
    """Turn "Amsterdam (Schiphol)" into a schema.org Airport object.

    Same convention as transavia-delay.py: airport name inside the
    parens, city outside; the IATA code is filled in by the caller
    since it appears on a separate line.
    """
    m = re.match(r"^\s*(.*?)\s*\(([^)]+)\)\s*$", phrase)
    if m:
        return {
            "@type": "Airport",
            "name": m.group(2).strip(),
            "address": m.group(1).strip(),
        }
    return {"@type": "Airport", "name": phrase.strip()}


def parse_leg_date(day: str, month: str, year: str, time: str) -> datetime | None:
    month_num = _MONTHS.get(month.lower())
    if month_num is None:
        return None
    try:
        return datetime.strptime(
            f"{year}-{month_num:02d}-{int(day):02d} {time}", "%Y-%m-%d %H:%M"
        )
    except ValueError:
        return None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html)

    booking = BOOKING_RE.search(text)
    if not booking:
        return 0
    booking_code = booking.group(1)

    for m in LEG_RE.finditer(text):
        (
            day,
            month,
            year,
            dep_time,
            arr_time,
            origin_phrase,
            dest_phrase,
            origin_iata,
            dest_iata,
            airline_iata,
            flight_num,
        ) = m.groups()

        dep = parse_leg_date(day, month, year, dep_time)
        arr = parse_leg_date(day, month, year, arr_time)
        if dep is None or arr is None:
            continue
        # Overnight legs: arrival past midnight rolls to next day.
        if arr < dep:
            arr += timedelta(days=1)

        origin = airport_from_phrase(origin_phrase)
        origin["iataCode"] = origin_iata
        dest = airport_from_phrase(dest_phrase)
        dest["iataCode"] = dest_iata

        flight_no = f"{airline_iata}{flight_num}"
        reservation = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": booking_code,
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": flight_num,
                "airline": {
                    "@type": "Airline",
                    "iataCode": airline_iata,
                    "name": "Transavia",
                },
                "departureAirport": origin,
                "arrivalAirport": dest,
                "departureTime": dep.strftime("%Y-%m-%dT%H:%M:%S"),
                "arrivalTime": arr.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }

        slug = f"transavia-{booking_code}-{flight_no}".lower()
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
