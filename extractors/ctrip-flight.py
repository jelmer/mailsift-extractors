#!/usr/bin/env python3
"""Ctrip (now Trip.com) flight reservation confirmations.

`english_flight_support@ctrip.com` sends "Flight reservation
confirmation" once the tickets are issued. After stripping tags the
body reads:

    Booking No.
    1234567890
    PNR
    ABC123
    Departure
    Jan 14 2018 CZ3540
    15:50 SHA Shanghai Hongqiao International Airport T2
    18:25 CAN Guangzhou Baiyun International Airport
    Jan 14 2018 CZ325
    21:00 CAN Guangzhou Baiyun International Airport
    09:25 SYD Sydney Kingsford Smith Airport T1
    Baggage Info
    ...
    Passenger / Ticket No.
    SURNAME/GIVEN NAMES
    784-1234567890
    Total amount
    CNY 3,468.00

Each segment carries only its departure date; an arrival time earlier
than the departure means the flight lands the next day. Codeshares add
the operating flight in parentheses (`MU9811 (FM811)`); we report the
marketing flight, which is what the ticket is issued on.

The Ctrip booking number is the reservation number, since Ctrip's
follow-up mails (refunds, e-receipts) refer to that rather than the
airline PNR.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

# Ctrip's mail was not DKIM-signed; its successor Trip.com signs
# everything it sends now. Nothing genuine from ctrip.com should
# postdate the rebrand.
CUTOFF = datetime(2019, 1, 1)

BOOKING_RE = re.compile(r"^Booking No\.\n(\d+)$", re.MULTILINE)
SEGMENT_RE = re.compile(
    r"^(?P<date>[A-Z][a-z]{2} \d{1,2} \d{4}) (?P<airline>[A-Z0-9]{2})(?P<number>\d{1,4})"
    r"(?: \((?P<operating>[A-Z0-9]{2}\d{1,4})\))?\n"
    r"(?P<dep_time>\d{2}:\d{2}) (?P<dep_iata>[A-Z]{3}) (?P<dep_name>.+)\n"
    r"(?P<arr_time>\d{2}:\d{2}) (?P<arr_iata>[A-Z]{3}) (?P<arr_name>.+)$",
    re.MULTILINE,
)
TERMINAL_RE = re.compile(r"^(.+?) (T\d+[A-Z]?)$")
PASSENGERS_RE = re.compile(
    r"^Passenger / Ticket No\.\n(.+?)\nTotal amount$", re.MULTILINE | re.DOTALL
)
TICKET_NUMBER_RE = re.compile(r"^\d{3}-\d{10}$")
TOTAL_RE = re.compile(r"^Total amount\n([A-Z]{3}) ([0-9,]+(?:\.\d+)?)$", re.MULTILINE)
MANAGE_URL_RE = re.compile(
    r'href="(https?://english\.ctrip\.com/flights/vieworder\?[^"]+)"', re.IGNORECASE
)


def airport(iata: str, phrase: str) -> dict:
    """Build an Airport node from "Shanghai Hongqiao ... Airport T2"."""
    node: dict = {"@type": "Airport", "iataCode": iata}
    terminal = TERMINAL_RE.match(phrase)
    if terminal:
        node["name"] = terminal.group(1)
        node["alternateName"] = terminal.group(2)
    else:
        node["name"] = phrase
    return node


def passengers(text: str) -> list[str]:
    """Passenger names, dropping the ticket number listed after each."""
    block = PASSENGERS_RE.search(text)
    if not block:
        return []
    return [
        line
        for line in block.group(1).split("\n")
        if line and not TICKET_NUMBER_RE.match(line)
    ]


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    # The manifest can't require DKIM, so refuse anything recent
    # enough that it ought to have been signed.
    if mail.date is None or mail.date.replace(tzinfo=None) >= CUTOFF:
        return 0

    text = "\n".join(
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    )

    booking = BOOKING_RE.search(text)
    if not booking:
        return 0
    reference = booking.group(1)

    segments = list(SEGMENT_RE.finditer(text))
    if not segments:
        return 0

    names = passengers(text)
    total = TOTAL_RE.search(text)
    manage = MANAGE_URL_RE.search(mail.html)

    for index, segment in enumerate(segments):
        day = datetime.strptime(segment.group("date"), "%b %d %Y")
        departs = datetime.combine(
            day, datetime.strptime(segment.group("dep_time"), "%H:%M").time()
        )
        arrives = datetime.combine(
            day, datetime.strptime(segment.group("arr_time"), "%H:%M").time()
        )
        if arrives < departs:
            arrives += timedelta(days=1)

        airline = segment.group("airline")
        number = segment.group("number")
        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": reference,
            "broker": {"@type": "Organization", "name": "Ctrip"},
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": number,
                "airline": {"@type": "Airline", "iataCode": airline},
                "departureAirport": airport(
                    segment.group("dep_iata"), segment.group("dep_name")
                ),
                "arrivalAirport": airport(
                    segment.group("arr_iata"), segment.group("arr_name")
                ),
                "departureTime": departs.strftime("%Y-%m-%dT%H:%M:%S"),
                "arrivalTime": arrives.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        if names:
            reservation["underName"] = [
                {"@type": "Person", "name": name} for name in names
            ]
        if manage:
            reservation["url"] = manage.group(1).replace("&amp;", "&")
        # The total covers the whole booking, so only the first segment
        # carries it.
        if total and index == 0:
            reservation["totalPrice"] = {
                "@type": "PriceSpecification",
                "price": float(total.group(2).replace(",", "")),
                "priceCurrency": total.group(1),
            }

        Path(f"ctrip-{reference}-{airline}{number}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
