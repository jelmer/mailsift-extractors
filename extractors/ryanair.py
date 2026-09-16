#!/usr/bin/env python3
"""Ryanair travel itineraries.

`Itinerary@ryanair.com` sends one mail per booking. After stripping
tags the flight block reads:

    Reservation:
    <PNR>
    ...
    To <destination> <flight number>
    <origin> -
    <destination>
    <Ddd, DD Mon YY>
    Departure time - HH:MM
    Arrival time - HH:MM
    (<IATA>) -
    (<IATA>)

A return booking repeats the block, so each flight becomes its own
`FlightReservation`. The year is two digits, which `%y` reads as
2000-2068 - fine for a booking mail, which is never about the 1900s.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

RESERVATION_RE = re.compile(r"^Reservation:\s*\n\s*([A-Z0-9]{5,8})\s*$", re.MULTILINE)
FLIGHT_RE = re.compile(r"^To\s+.+?\s+([A-Z]{2}\d{1,4})\s*$", re.MULTILINE)
DATE_RE = re.compile(r"^\w{3},\s*(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2})\s*$", re.MULTILINE)
DEPART_RE = re.compile(r"Departure time\s*-\s*(\d{1,2}):(\d{2})")
ARRIVE_RE = re.compile(r"Arrival time\s*-\s*(\d{1,2}):(\d{2})")
IATA_RE = re.compile(r"^\(([A-Z]{3})\)\s*-?\s*$", re.MULTILINE)
TOTAL_RE = re.compile(r"([0-9]+(?:\.[0-9]{2})?)\s+([A-Z]{3})\s*$", re.MULTILINE)


def parse_leg(window: str) -> dict | None:
    flight = FLIGHT_RE.search(window)
    date = DATE_RE.search(window)
    depart = DEPART_RE.search(window)
    if not flight or not date or not depart:
        return None

    try:
        day = datetime.strptime(
            f"{date.group(1)} {date.group(2)} {date.group(3)}", "%d %b %y"
        )
    except ValueError:
        return None

    try:
        departs = day.replace(hour=int(depart.group(1)), minute=int(depart.group(2)))
    except ValueError:
        return None

    leg: dict = {"flight": flight.group(1), "departs": departs}

    arrive = ARRIVE_RE.search(window)
    if arrive:
        arrives = day.replace(hour=int(arrive.group(1)), minute=int(arrive.group(2)))
        # An arrival before departure means the flight crossed midnight.
        if arrives < departs:
            arrives += timedelta(days=1)
        leg["arrives"] = arrives

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

    reservation_match = RESERVATION_RE.search(text)
    if not reservation_match:
        return 0
    reference = reservation_match.group(1)

    headings = list(FLIGHT_RE.finditer(text))
    if not headings:
        return 0

    legs = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        leg = parse_leg(text[heading.start() : end])
        if leg is not None:
            legs.append(leg)
    if not legs:
        return 0

    total = TOTAL_RE.search(text)

    for index, leg in enumerate(legs):
        flight: dict = {
            "@type": "Flight",
            "airline": {"@type": "Airline", "name": "Ryanair", "iataCode": "FR"},
            "flightNumber": leg["flight"],
            "departureTime": leg["departs"].strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if "arrives" in leg:
            flight["arrivalTime"] = leg["arrives"].strftime("%Y-%m-%dT%H:%M:%S")
        if "origin" in leg:
            flight["departureAirport"] = {
                "@type": "Airport",
                "iataCode": leg["origin"],
            }
            flight["arrivalAirport"] = {
                "@type": "Airport",
                "iataCode": leg["destination"],
            }

        booking: dict = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": reference,
            "reservationFor": flight,
        }
        # The receipt total covers the whole booking, so it stays on the
        # first leg rather than being repeated per flight.
        if total is not None and index == 0:
            booking["totalPrice"] = {
                "@type": "PriceSpecification",
                "price": float(total.group(1)),
                "priceCurrency": total.group(2),
            }

        suffix = f"-{index + 1}" if len(legs) > 1 else ""
        Path(f"ryanair-{reference.lower()}{suffix}.reservation.json").write_text(
            json.dumps(booking, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
