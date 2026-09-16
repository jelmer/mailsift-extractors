#!/usr/bin/env python3
"""Delta Air Lines flight receipts.

`DeltaAirLines@e.delta.com` sends a "Your Flight Receipt" mail per
booking. After stripping tags each flight reads:

    <Ddd, DDMMM>
    DEPART
    ARRIVE
    DELTA AIR LINES INC <number>*
    <cabin>
    <origin city>
    <H:MMam/pm>
    <destination city>
    <H:MMam/pm>

The body's date carries no year - only the subject does, as the
`DDMMMYY` suffix of `Your Flight Receipt - <name> 06MAY17` - so the
year is taken from there and applied to every leg.

Delta names cities rather than IATA codes here, so the airports carry
a `name` and no `iataCode`.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

SUBJECT_YEAR_RE = re.compile(r"\b\d{1,2}[A-Z]{3}(\d{2})\s*$")
CONFIRMATION_RE = re.compile(r"Trip Confirmation #:\s*([A-Z0-9]{5,8})")
LEG_RE = re.compile(r"^\w{3},\s*(\d{1,2})([A-Z]{3})\s*$", re.MULTILINE)
FLIGHT_RE = re.compile(r"^DELTA AIR LINES INC\s+(\d{1,4})\*?\s*$", re.MULTILINE)
CLOCK_RE = re.compile(r"^(\d{1,2}):(\d{2})(am|pm)\s*$", re.MULTILINE | re.IGNORECASE)
PLACE_RE = re.compile(r"^([A-Z][A-Z .'-]*(?:,\s*[A-Z]{2})?)\s*$", re.MULTILINE)
TOTAL_RE = re.compile(r"TICKET AMOUNT\s*\n\s*\$([0-9,]+(?:\.[0-9]{2})?)\s*([A-Z]{3})")

SKIP_PLACES = {"DEPART", "ARRIVE", "FLIGHT", "SEAT", "NAME"}


def to_24h(hour: str, minute: str, meridiem: str) -> tuple[int, int]:
    value = int(hour)
    if meridiem.lower() == "pm" and value != 12:
        value += 12
    elif meridiem.lower() == "am" and value == 12:
        value = 0
    return (value, int(minute))


def parse_leg(window: str, day: str, month: str, year: int) -> dict | None:
    flight = FLIGHT_RE.search(window)
    if not flight:
        return None

    try:
        date = datetime.strptime(f"{day} {month} {year}", "%d %b %Y")
    except ValueError:
        return None

    clocks = CLOCK_RE.findall(window)
    if len(clocks) < 2:
        return None

    dep_hh, dep_mm = to_24h(*clocks[0])
    arr_hh, arr_mm = to_24h(*clocks[1])
    departs = date.replace(hour=dep_hh, minute=dep_mm)
    arrives = date.replace(hour=arr_hh, minute=arr_mm)
    # A red-eye lands the next day; the header names the departure date.
    if arrives < departs:
        arrives += timedelta(days=1)

    places = [p.strip() for p in PLACE_RE.findall(window)]
    places = [p for p in places if p not in SKIP_PLACES and not p.startswith("DELTA")]

    leg: dict = {
        "flight": f"DL{flight.group(1)}",
        "departs": departs,
        "arrives": arrives,
    }
    if len(places) >= 2:
        leg["origin"] = places[0]
        leg["destination"] = places[1]
    return leg


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    year_match = SUBJECT_YEAR_RE.search(mail.subject or "")
    if not year_match:
        return 0
    year = 2000 + int(year_match.group(1))

    text = strip_html(mail.html, block_tags=True)

    confirmation = CONFIRMATION_RE.search(text)
    if not confirmation:
        return 0
    reference = confirmation.group(1)

    headings = list(LEG_RE.finditer(text))
    if not headings:
        return 0

    legs = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        leg = parse_leg(
            text[heading.end() : end], heading.group(1), heading.group(2), year
        )
        if leg is not None:
            legs.append(leg)
    if not legs:
        return 0

    total = TOTAL_RE.search(text)

    for index, leg in enumerate(legs):
        flight: dict = {
            "@type": "Flight",
            "airline": {
                "@type": "Airline",
                "name": "Delta Air Lines",
                "iataCode": "DL",
            },
            "flightNumber": leg["flight"],
            "departureTime": leg["departs"].strftime("%Y-%m-%dT%H:%M:%S"),
            "arrivalTime": leg["arrives"].strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if "origin" in leg:
            flight["departureAirport"] = {"@type": "Airport", "name": leg["origin"]}
            flight["arrivalAirport"] = {"@type": "Airport", "name": leg["destination"]}

        booking: dict = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": reference,
            "reservationFor": flight,
        }
        if total is not None and index == 0:
            booking["totalPrice"] = {
                "@type": "PriceSpecification",
                "price": float(total.group(1).replace(",", "")),
                "priceCurrency": total.group(2),
            }

        suffix = f"-{index + 1}" if len(legs) > 1 else ""
        Path(f"delta-{reference.lower()}{suffix}.reservation.json").write_text(
            json.dumps(booking, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
