#!/usr/bin/env python3
"""Vueling booking confirmations.

`no-reply@vueling.com` sends a confirmation per booking. After
stripping tags each flight block reads:

    Booking code <PNR>
    Outbound
    <fare>
    <Weekday, D Month YYYY>
    <origin city>
    <destination city>
    <IATA>
    <IATA>
    HH:MMh
    HH:MMh
    <flight number>

A return booking repeats the block under `Return`, so each flight
becomes its own `FlightReservation`. Times carry a trailing `h`.

The same address also sends boarding passes and reminders; the
manifest's subject match keeps those out.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

BOOKING_RE = re.compile(r"Booking code\s+([A-Z0-9]{5,8})")
LEG_RE = re.compile(r"^(Outbound|Return)\s*$", re.MULTILINE)
DATE_RE = re.compile(r"^\w+,\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*$", re.MULTILINE)
IATA_RE = re.compile(r"^([A-Z]{3})\s*$", re.MULTILINE)
CLOCK_RE = re.compile(r"^(\d{1,2}):(\d{2})h\s*$", re.MULTILINE)
FLIGHT_RE = re.compile(r"^(VY\d{1,4})\s*$", re.MULTILINE)
TOTAL_RE = re.compile(r"Total:\s*([0-9]+(?:\.[0-9]{2})?)\s*([A-Z]{3})")


def parse_leg(window: str) -> dict | None:
    date = DATE_RE.search(window)
    flight = FLIGHT_RE.search(window)
    clocks = CLOCK_RE.findall(window)
    if not date or not flight or len(clocks) < 2:
        return None

    for fmt in ("%B", "%b"):
        try:
            day = datetime.strptime(
                f"{date.group(1)} {date.group(2)} {date.group(3)}", f"%d {fmt} %Y"
            )
        except ValueError:
            continue
        break
    else:
        return None

    departs = day.replace(hour=int(clocks[0][0]), minute=int(clocks[0][1]))
    arrives = day.replace(hour=int(clocks[1][0]), minute=int(clocks[1][1]))
    if arrives < departs:
        arrives += timedelta(days=1)

    leg: dict = {
        "flight": flight.group(1),
        "departs": departs,
        "arrives": arrives,
    }
    codes = IATA_RE.findall(window)
    if len(codes) >= 2:
        leg["origin"] = codes[0]
        leg["destination"] = codes[1]
    return leg


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html, block_tags=True)

    booking = BOOKING_RE.search(text)
    if not booking:
        return 0
    reference = booking.group(1)

    headings = list(LEG_RE.finditer(text))
    if not headings:
        return 0

    legs = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        leg = parse_leg(text[heading.end() : end])
        if leg is not None:
            legs.append(leg)
    if not legs:
        return 0

    total = TOTAL_RE.search(text)

    for index, leg in enumerate(legs):
        flight: dict = {
            "@type": "Flight",
            "airline": {"@type": "Airline", "name": "Vueling", "iataCode": "VY"},
            "flightNumber": leg["flight"],
            "departureTime": leg["departs"].strftime("%Y-%m-%dT%H:%M:%S"),
            "arrivalTime": leg["arrives"].strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if "origin" in leg:
            flight["departureAirport"] = {
                "@type": "Airport",
                "iataCode": leg["origin"],
            }
            flight["arrivalAirport"] = {
                "@type": "Airport",
                "iataCode": leg["destination"],
            }

        booking_json: dict = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": reference,
            "reservationFor": flight,
        }
        if total is not None and index == 0:
            booking_json["totalPrice"] = {
                "@type": "PriceSpecification",
                "price": float(total.group(1)),
                "priceCurrency": total.group(2),
            }

        suffix = f"-{index + 1}" if len(legs) > 1 else ""
        Path(f"vueling-{reference.lower()}{suffix}.reservation.json").write_text(
            json.dumps(booking_json, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
