#!/usr/bin/env python3
"""Carlson Wagonlit (CWT) "Travel documents for ..." mails, as sent in 2012.

The later "Trip document (e-ticket receipt)" mails from mycwt.com embed
schema.org JSON-LD, which `schema-ld` already reads, so they're left
to it.

After tag-stripping, each segment is a run of label and value lines
after a day header:

    Wed 15 August, 2040
    E-Ticket
    0750000000002 |
    ...
    Flight IBERIA
    IB3170
    DEPARTURE
    Madrid
    (MAD)
    ARRIVAL
    Lisbon
    (LIS)
    10:05 -
    15/08/2040
    11:25 -
    15/08/2040
    Booking status
    Confirmed

and hotels read "Confirmation <number>", "Hotel <name>", "LOCATION",
<address>, ..., "Night(s)", <count>.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

STATUSES = {
    "confirmed": "https://schema.org/ReservationConfirmed",
    "cancelled": "https://schema.org/ReservationCancelled",
}

LOCATOR_RE = re.compile(r"^Trip locator: ([A-Z0-9]{6})$")
FLIGHT_NUMBER_RE = re.compile(r"^([A-Z0-9]{2})(\d{1,4})$")
IATA_RE = re.compile(r"^\(([A-Z]{3})\)$")
TIME_RE = re.compile(r"^(\d{2}:\d{2}) -$")
DAY_RE = re.compile(r"^\w{3} (\d{2} \w+, \d{4})$")


def status_of(value: str) -> str:
    try:
        return STATUSES[value.strip().lower()]
    except KeyError:
        raise ValueError(f"unknown booking status {value!r}") from None


def value_after(lines: list[str], start: int, label: str) -> int:
    for i in range(start, len(lines)):
        if lines[i] == label:
            return i + 1
    raise ValueError(f"no {label!r} after line {start}")


def parse_flight(lines: list[str], i: int) -> tuple[dict, str]:
    """(flight, status) for the "Flight <airline>" line at `lines[i]`."""
    number = FLIGHT_NUMBER_RE.match(lines[i + 1])
    if not number:
        raise ValueError(f"no flight number after {lines[i]!r}")
    dep = value_after(lines, i, "DEPARTURE")
    arr = value_after(lines, dep, "ARRIVAL")
    origin = IATA_RE.match(lines[dep + 1])
    destination = IATA_RE.match(lines[arr + 1])
    dep_time = TIME_RE.match(lines[arr + 2])
    arr_time = TIME_RE.match(lines[arr + 4])
    if not origin or not destination or not dep_time or not arr_time:
        raise ValueError(f"unrecognised segment after {lines[i]!r}")
    departs = datetime.strptime(
        f"{lines[arr + 3]} {dep_time.group(1)}", "%d/%m/%Y %H:%M"
    )
    arrives = datetime.strptime(
        f"{lines[arr + 5]} {arr_time.group(1)}", "%d/%m/%Y %H:%M"
    )
    segment = {
        "@type": "Flight",
        "flightNumber": number.group(2),
        "airline": {
            "@type": "Airline",
            "iataCode": number.group(1),
            "name": lines[i].removeprefix("Flight ").title(),
        },
        "departureAirport": {"@type": "Airport", "iataCode": origin.group(1)},
        "arrivalAirport": {"@type": "Airport", "iataCode": destination.group(1)},
        "departureTime": departs.strftime("%Y-%m-%dT%H:%M:%S"),
        "arrivalTime": arrives.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return segment, status_of(lines[value_after(lines, arr, "Booking status")])


def parse_hotel(lines: list[str], i: int, day: datetime) -> dict:
    """The hotel whose "Confirmation <number>" line is `lines[i]`."""
    nights = int(lines[value_after(lines, i, "Night(s)")])
    return {
        "@type": "LodgingReservation",
        "reservationNumber": lines[i].removeprefix("Confirmation "),
        "reservationStatus": status_of(lines[value_after(lines, i, "Booking status")]),
        "checkinTime": day.strftime("%Y-%m-%d"),
        "checkoutTime": (day + timedelta(days=nights)).strftime("%Y-%m-%d"),
        "reservationFor": {
            "@type": "LodgingBusiness",
            "name": lines[i + 1].removeprefix("Hotel ").title(),
            "address": lines[value_after(lines, i, "LOCATION")].title(),
        },
    }


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]
    locator = next(
        (m.group(1) for line in lines if (m := LOCATOR_RE.match(line))), None
    )
    if locator is None:
        return 0
    common: dict = {
        "@context": "https://schema.org",
        "broker": {"@type": "Organization", "name": "CWT"},
    }
    try:
        name = lines[lines.index("Traveler") + 1]
    except (ValueError, IndexError):
        pass
    else:
        name = re.sub(r"^(?:Mr|Mrs|Ms|Miss|Dr) ", "", name)
        common["underName"] = {
            "@type": "Person",
            "name": " ".join(part.capitalize() for part in name.split()),
        }

    outputs: dict[str, dict] = {}
    day = None
    for i, line in enumerate(lines[:-1]):
        if m := DAY_RE.match(line):
            day = datetime.strptime(m.group(1), "%d %B, %Y")
        elif line.startswith("Flight ") and FLIGHT_NUMBER_RE.match(lines[i + 1]):
            segment, status = parse_flight(lines, i)
            reservation = {
                "@type": "FlightReservation",
                "reservationNumber": locator,
                "reservationStatus": status,
                "reservationFor": segment,
                **common,
            }
            ticket = next(
                (
                    lines[j + 1].removesuffix(" |")
                    for j in range(max(i - 6, 0), i)
                    if lines[j] == "E-Ticket"
                ),
                None,
            )
            if ticket:
                reservation["ticketNumber"] = ticket
            stamp = segment["departureTime"][:10].replace("-", "")
            origin = segment["departureAirport"]["iataCode"]
            outputs[f"cwt-{locator}-{stamp}-{origin}"] = reservation
        elif line.startswith("Confirmation ") and lines[i + 1].startswith("Hotel "):
            if day is None:
                raise ValueError(f"hotel {line!r} before any day header")
            hotel = parse_hotel(lines, i, day)
            outputs[f"cwt-{locator}-{hotel['reservationNumber']}"] = {**hotel, **common}
    if not outputs:
        raise ValueError(f"trip {locator} lists nothing we can read")
    for name, doc in outputs.items():
        Path(f"{name}.reservation.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
