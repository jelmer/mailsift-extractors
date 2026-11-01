#!/usr/bin/env python3
"""Ctrip (now Trip.com) China rail "Ticket Issued" mails.

`train_reservation@ctrip.com` sends one per booking once the tickets
are issued. Each booking covers a single train; after stripping tags
the body reads:

    Booking No.
    E123456789
    ...
    Itinerary
    Beijing South -Shanghai Hongqiao (Train Number:G13)
    Departure Time: 10:00 12 Jan, 2018
    Arrival Time: 14:28 12 Jan, 2018
    Passengers
    SURNAME GIVEN(Passport X1234567) (Carriage 14, Seat no. 03A)
    ...
    Total
    CNY
    1,139

The stations are joined by a bare hyphen with inconsistent spacing
(`Beijing South -Shanghai Hongqiao`, `Pingyao County High-speed-Beijing
West`), and station names may themselves contain hyphens. Ctrip writes
station names in title case, so the separator is the one hyphen
followed by a capital letter.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

BOOKING_RE = re.compile(r"^Booking No\.\n(E\d+)$", re.MULTILINE)
ROUTE_RE = re.compile(
    r"^Itinerary\n(?P<route>.+?)\s*\(Train Number:\s*(?P<train>[A-Z]*\d+)\)$",
    re.MULTILINE,
)
STATION_SEPARATOR_RE = re.compile(r"\s*-\s*(?=[A-Z])")
DEPARTURE_RE = re.compile(
    r"^Departure Time: (\d{2}:\d{2} \d{1,2} [A-Z][a-z]{2}, \d{4})$", re.MULTILINE
)
ARRIVAL_RE = re.compile(
    r"^Arrival Time: (\d{2}:\d{2} \d{1,2} [A-Z][a-z]{2}, \d{4})$", re.MULTILINE
)
PASSENGER_RE = re.compile(
    r"^(?P<name>[^\n(]+?)\s*\([^)]*\) \(Carriage (?P<carriage>\w+), Seat no\. (?P<seat>\w+)\)$",
    re.MULTILINE,
)
TOTAL_RE = re.compile(r"^Total\n([A-Z]{3})\s+([0-9,]+(?:\.\d+)?)$", re.MULTILINE)
MANAGE_URL_RE = re.compile(r'href="(https://english\.ctrip\.com/trains/order\?[^"]+)"')


class UnparseableRoute(Exception):
    """The itinerary line has no single station separator."""


def split_route(route: str) -> tuple[str, str]:
    separators = list(STATION_SEPARATOR_RE.finditer(route))
    if len(separators) != 1:
        raise UnparseableRoute(route)
    separator = separators[0]
    return route[: separator.start()].strip(), route[separator.end() :].strip()


def parse_time(value: str) -> str:
    return datetime.strptime(value, "%H:%M %d %b, %Y").strftime("%Y-%m-%dT%H:%M:%S")


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = "\n".join(
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    )

    booking = BOOKING_RE.search(text)
    route = ROUTE_RE.search(text)
    departure = DEPARTURE_RE.search(text)
    arrival = ARRIVAL_RE.search(text)
    if not (booking and route and departure and arrival):
        return 0
    reference = booking.group(1)
    origin, destination = split_route(route.group("route"))

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "TrainReservation",
        "reservationNumber": reference,
        "broker": {"@type": "Organization", "name": "Ctrip"},
        "reservationFor": {
            "@type": "TrainTrip",
            "trainNumber": route.group("train"),
            "departureStation": {"@type": "TrainStation", "name": origin},
            "arrivalStation": {"@type": "TrainStation", "name": destination},
            "departureTime": parse_time(departure.group(1)),
            "arrivalTime": parse_time(arrival.group(1)),
        },
    }

    passengers = list(PASSENGER_RE.finditer(text))
    if passengers:
        reservation["underName"] = [
            {"@type": "Person", "name": p.group("name")} for p in passengers
        ]
        # A Seat holds one seat, so a party only gets the carriage
        # when everyone shares it.
        carriages = {p.group("carriage") for p in passengers}
        seat: dict = {"@type": "Seat"}
        if len(carriages) == 1:
            seat["seatSection"] = carriages.pop()
        if len(passengers) == 1:
            seat["seatNumber"] = passengers[0].group("seat")
        if len(seat) > 1:
            reservation["ticketedSeat"] = seat

    manage = MANAGE_URL_RE.search(mail.html)
    if manage:
        reservation["url"] = manage.group(1).replace("&amp;", "&")

    total = TOTAL_RE.search(text)
    if total:
        reservation["totalPrice"] = {
            "@type": "PriceSpecification",
            "price": float(total.group(2).replace(",", "")),
            "priceCurrency": total.group(1),
        }

    Path(f"ctrip-{reference}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
