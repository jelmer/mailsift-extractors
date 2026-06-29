#!/usr/bin/env python3
"""easyJet flight booking confirmations.

The "easyJet booking reference: XXXXXX" mail enumerates each leg of the
trip as:

    <N> of <M> <Origin> to <Destination> <FLIGHTNUM>
    Departs: <Day DD Mon YYYY HH:MM>
    Arrives: <Day DD Mon YYYY HH:MM>

We emit one FlightReservation per leg, keyed off the booking reference
+ flight number so a "your flight has been moved" update overwrites the
existing event rather than creating a duplicate.
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


REFERENCE_RE = re.compile(r"easyJet booking reference:?\s*([A-Z0-9]+)", re.I)

LEG_RE = re.compile(
    r"(\d+)\s+of\s+(\d+)\s+([A-Z][A-Za-z .'-]+?)\s+to\s+([A-Z][A-Za-z .'-]+?)\s+"
    r"(EZ[YS]?\d+)\s+"
    r"Departs:\s+([A-Z][a-z]+\s+\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\s+\d{1,2}:\d{2})\s+"
    r"Arrives:\s+([A-Z][a-z]+\s+\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\s+\d{1,2}:\d{2})"
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


def parse_dt(s: str) -> datetime | None:
    # "Fri 12 Jul 2024 18:45"
    try:
        return datetime.strptime(s.strip(), "%a %d %b %Y %H:%M")
    except ValueError:
        return None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html)

    ref_match = REFERENCE_RE.search(mail.subject or "") or REFERENCE_RE.search(text)
    if not ref_match:
        return 0
    reference = ref_match.group(1)

    legs = list(LEG_RE.finditer(text))
    if not legs:
        return 0

    for leg in legs:
        _, _, origin, dest, flight_no, dep_s, arr_s = leg.groups()
        dep = parse_dt(dep_s)
        arr = parse_dt(arr_s)
        if dep is None or arr is None:
            continue
        if arr < dep:
            continue

        # easyJet's flight number is e.g. "EZY2521". Split into airline +
        # number so the converter can render "Flight EZY2521: ..." rather
        # than just "Flight 2521".
        m = re.match(r"([A-Z]+)(\d+)", flight_no)
        if m:
            airline_code, num = m.group(1), m.group(2)
        else:
            airline_code, num = "", flight_no

        reservation = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": f"easyjet-{reference}-{flight_no}",
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": num,
                "airline": {"@type": "Airline", "iataCode": airline_code},
                "departureAirport": {"@type": "Airport", "name": origin},
                "arrivalAirport": {"@type": "Airport", "name": dest},
                "departureTime": dep.strftime("%Y-%m-%dT%H:%M:%S"),
                "arrivalTime": arr.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }

        slug = f"easyjet-{reference}-{flight_no}".lower()
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
