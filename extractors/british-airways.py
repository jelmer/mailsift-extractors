#!/usr/bin/env python3
"""British Airways e-ticket receipts.

BA's e-ticket mail (BA.e-ticket@email.ba.com) carries a clean
plain-text itinerary. We don't try to extract from HTML, which is
designed for visual layout and would be fragile to scrape.

Format:

    British Airways booking reference: BBBBBB
    ...
    --------------
    Your Itinerary
    --------------
    ----------------------------------------------------
    BA0440: British Airways | Euro Traveller | Confirmed
    ----------------------------------------------------
    Depart: 8 Jun 2024 16:15 - Heathrow (London) - Terminal 5
    Arrive: 8 Jun 2024 18:35 - Amsterdam

Each `BAnnnn:` segment becomes one `FlightReservation` sharing the
booking reference. Subsequent updates (delay, cancellation) sent by
other BA addresses would land on a different extractor; here we only
process the one-shot e-ticket receipt.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


BOOKING_RE = re.compile(r"British Airways booking reference:\s*([A-Z0-9]{5,8})")
SEGMENT_RE = re.compile(
    r"^(BA\d{2,4}):\s*British Airways\b",
    re.MULTILINE,
)
DEPART_RE = re.compile(
    r"^Depart:\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+(\d{1,2}:\d{2})\s*-\s*(.+?)\s*$",
    re.MULTILINE,
)
ARRIVE_RE = re.compile(
    r"^Arrive:\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+(\d{1,2}:\d{2})\s*-\s*(.+?)\s*$",
    re.MULTILINE,
)


def parse_naive_dt(date_str: str, time_str: str) -> datetime | None:
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%d %b %Y %H:%M")
    except ValueError:
        return None


def airport_from_phrase(phrase: str) -> dict:
    """Turn "Heathrow (London) - Terminal 5" or "Amsterdam" into an
    Airport object.

    BA writes the airport name first; the parenthesised city follows;
    everything after a ` - ` is a terminal annotation we keep on the
    address field.
    """
    text = phrase.strip()
    terminal = None
    if " - " in text:
        text, terminal = text.split(" - ", 1)
        terminal = terminal.strip()
    name = text.strip()
    address = None
    m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", name)
    if m:
        name = m.group(1).strip()
        address = m.group(2).strip()
    out: dict = {"@type": "Airport", "name": name}
    if address:
        out["address"] = address
    if terminal:
        out["alternateName"] = terminal
    return out


def main() -> int:
    mail = read_message()
    text = mail.text
    if not text:
        return 0

    booking_match = BOOKING_RE.search(text)
    if not booking_match:
        return 0
    booking_code = booking_match.group(1)

    # Walk segments by their `BAnnnn:` header. The body between one
    # header and the next holds that segment's Depart/Arrive lines.
    headers = list(SEGMENT_RE.finditer(text))
    if not headers:
        return 0

    for index, header in enumerate(headers):
        flight_no = header.group(1)  # e.g. "BA0440"
        block_start = header.end()
        block_end = (
            headers[index + 1].start() if index + 1 < len(headers) else len(text)
        )
        block = text[block_start:block_end]

        dep_match = DEPART_RE.search(block)
        arr_match = ARRIVE_RE.search(block)
        if not dep_match or not arr_match:
            continue
        dep_dt = parse_naive_dt(dep_match.group(1), dep_match.group(2))
        arr_dt = parse_naive_dt(arr_match.group(1), arr_match.group(2))
        if dep_dt is None or arr_dt is None:
            continue

        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": booking_code,
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": flight_no[2:].lstrip("0") or "0",
                "airline": {
                    "@type": "Airline",
                    "iataCode": "BA",
                    "name": "British Airways",
                },
                "departureAirport": airport_from_phrase(dep_match.group(3)),
                "arrivalAirport": airport_from_phrase(arr_match.group(3)),
                "departureTime": dep_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "arrivalTime": arr_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        Path(f"ba-{booking_code}-{flight_no}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
