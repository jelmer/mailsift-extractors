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

Older mails used other layouts, each handled by its own parser:

- 2018: "Reservation:" too, but each flight is a "To"/"From" block of
  label lines ("Depart:", "(BRS)", "Date:", "Mon, 16 Apr 46",
  "Time:", "18:30", "Arrival:", ...).
- 2015: "FLIGHT RESERVATION NUMBER" then the PNR; each flight is
  "(FR1022)", "DEPART (GDN)", ..., "ARRIVAL (DUB)", ..., then the
  departure and arrival dates, each followed by "HH:MMhrs".
- 2011: "YOUR RESERVATION NUMBER IS: <PNR>", and one line per flight:
  "Mon, 30May39 Flight FR3124 Depart FAO at 16:45 and arrive BRE at
  19:50".
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

BLOCK_2018_RE = re.compile(
    r"^(?:To|From)\n.+\n([A-Z]{2}) (\d{1,4})\nDepart:\n.+\n\(([A-Z]{3})\)\n"
    r"Date:\n\w{3}, (\d{1,2} \w{3} \d{2})\nTime:\n(\d{1,2}:\d{2})\n"
    r"Arrival:\n.+\n\(([A-Z]{3})\)\n"
    r"Date:\n\w{3}, (\d{1,2} \w{3} \d{2})\nTime:\n(\d{1,2}:\d{2})$",
    re.MULTILINE,
)
RESERVATION_2015_RE = re.compile(
    r"^FLIGHT RESERVATION NUMBER\n([A-Z0-9]{6})$", re.MULTILINE
)
BLOCK_2015_RE = re.compile(
    r"^\(([A-Z]{2})(\d{1,4})\)\nDEPART \(([A-Z]{3})\)\n.+\nARRIVAL \(([A-Z]{3})\)\n.+\n"
    r"\w{3} (\d{1,2} \w{3} \d{4})\n(\d{1,2}:\d{2})hrs\n"
    r"\w{3} (\d{1,2} \w{3} \d{4})\n(\d{1,2}:\d{2})hrs$",
    re.MULTILINE,
)
RESERVATION_2011_RE = re.compile(
    r"^YOUR RESERVATION NUMBER IS: ([A-Z0-9]{6})$", re.MULTILINE
)
LINE_2011_RE = re.compile(
    r"^\w{3}, (\d{1,2}[A-Za-z]{3}\d{2}) Flight ([A-Z]{2})(\d{1,4}) "
    r"Depart ([A-Z]{3}) at (\d{1,2}:\d{2}) and arrive ([A-Z]{3}) at (\d{1,2}:\d{2})$",
    re.MULTILINE,
)


def stamp(day: str, time: str, fmt: str) -> datetime:
    return datetime.strptime(f"{day} {time}", f"{fmt} %H:%M")


def legacy_legs(text: str) -> tuple[str, list[dict]] | None:
    """The PNR and flights of a pre-2019 itinerary, if this is one."""
    reservation = RESERVATION_RE.search(text)
    blocks = list(BLOCK_2018_RE.finditer(text))
    if reservation and blocks:
        return reservation.group(1), [
            {
                "flight": m.group(1) + m.group(2),
                "origin": m.group(3),
                "departs": stamp(m.group(4), m.group(5), "%d %b %y"),
                "destination": m.group(6),
                "arrives": stamp(m.group(7), m.group(8), "%d %b %y"),
            }
            for m in blocks
        ]
    reservation = RESERVATION_2015_RE.search(text)
    if reservation:
        return reservation.group(1), [
            {
                "flight": m.group(1) + m.group(2),
                "origin": m.group(3),
                "destination": m.group(4),
                "departs": stamp(m.group(5), m.group(6), "%d %b %Y"),
                "arrives": stamp(m.group(7), m.group(8), "%d %b %Y"),
            }
            for m in BLOCK_2015_RE.finditer(text)
        ]
    reservation = RESERVATION_2011_RE.search(text)
    if reservation:
        legs = []
        for m in LINE_2011_RE.finditer(text):
            departs = stamp(m.group(1), m.group(5), "%d%b%y")
            arrives = stamp(m.group(1), m.group(7), "%d%b%y")
            if arrives < departs:
                arrives += timedelta(days=1)
            legs.append(
                {
                    "flight": m.group(2) + m.group(3),
                    "origin": m.group(4),
                    "destination": m.group(6),
                    "departs": departs,
                    "arrives": arrives,
                }
            )
        return reservation.group(1), legs
    return None


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
    lines = "\n".join(line.strip() for line in text.splitlines() if line.strip())

    reservation_match = RESERVATION_RE.search(text)
    headings = list(FLIGHT_RE.finditer(text))
    if reservation_match and headings:
        reference = reservation_match.group(1)
        legs = []
        for index, heading in enumerate(headings):
            end = (
                headings[index + 1].start() if index + 1 < len(headings) else len(text)
            )
            leg = parse_leg(text[heading.start() : end])
            if leg is not None:
                legs.append(leg)
        total = TOTAL_RE.search(text)
    else:
        legacy = legacy_legs(lines)
        if legacy is None:
            return 0
        reference, legs = legacy
        if not legs:
            raise ValueError(f"itinerary {reference} lists no flights we can read")
        # TODO: read the totals of the pre-2019 layouts as well.
        total = None
    if not legs:
        return 0

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
