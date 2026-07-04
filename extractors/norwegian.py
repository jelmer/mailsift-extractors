#!/usr/bin/env python3
"""Norwegian Air Shuttle booking confirmations.

Sent from `noreply@norwegian.com` with subject `Travel Receipt` or
`Travel documents <CODE>`. The HTML body has no schema.org markup but
its rendered text has a regular per-segment block:

    Booking reference: CCCCCC
    ...
    DY1303-10 Jun 2025
    09:20 London-Gatwick
    12:25 Oslo-Gardermoen

We emit one `FlightReservation` per segment. The mail body doesn't
include the year on every header but the flight-number line does
(`DY1303-10 Jun 2025`), so we parse it directly without falling back
to the `Date:` header.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


BOOKING_RE = re.compile(r"Booking reference:\s*([A-Z0-9]{5,8})")
FLIGHT_HEADER_RE = re.compile(
    r"^(DY\d{2,4})\s*-\s*(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})\s*$",
    re.MULTILINE,
)
TIME_AIRPORT_RE = re.compile(
    r"^(\d{1,2}:\d{2})\s+(.+?)\s*$",
    re.MULTILINE,
)


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True
        elif tag in ("br", "tr", "p", "div", "h1", "h2", "h3", "td", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False
        elif tag in ("tr", "p", "div", "h1", "h2", "h3", "td", "li"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(body: str) -> str:
    p = _Strip()
    p.feed(body)
    text = "".join(p.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_dt(date_str: str, time_str: str) -> datetime | None:
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%d %b %Y %H:%M")
    except ValueError:
        return None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html)

    booking_match = BOOKING_RE.search(text)
    if not booking_match:
        return 0
    booking = booking_match.group(1)

    headers = list(FLIGHT_HEADER_RE.finditer(text))
    if not headers:
        return 0

    for index, header in enumerate(headers):
        flight_no = header.group(1)
        date_str = header.group(2)
        block_start = header.end()
        block_end = (
            headers[index + 1].start() if index + 1 < len(headers) else len(text)
        )
        block = text[block_start:block_end]

        # The first two TIME_AIRPORT_RE matches in the block are
        # departure and arrival, in that order.
        times = TIME_AIRPORT_RE.findall(block)
        if len(times) < 2:
            continue
        dep_time, dep_airport = times[0]
        arr_time, arr_airport = times[1]

        dep_dt = parse_dt(date_str, dep_time)
        arr_dt = parse_dt(date_str, arr_time)
        if dep_dt is None or arr_dt is None:
            continue
        if arr_dt < dep_dt:
            # Overnight flight: arrival is the next day.
            arr_dt = arr_dt.replace(day=arr_dt.day + 1)

        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": booking,
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": flight_no[2:].lstrip("0") or "0",
                "airline": {
                    "@type": "Airline",
                    "iataCode": "DY",
                    "name": "Norwegian",
                },
                "departureAirport": {
                    "@type": "Airport",
                    "name": dep_airport.strip(),
                },
                "arrivalAirport": {
                    "@type": "Airport",
                    "name": arr_airport.strip(),
                },
                "departureTime": dep_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "arrivalTime": arr_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        Path(f"norwegian-{booking}-{flight_no}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
