#!/usr/bin/env python3
"""British Airways e-ticket receipts.

BA's e-ticket mail (BA.e-ticket@email.ba.com) carries a clean
plain-text itinerary. We don't try to extract from HTML, which is
designed for visual layout and would be fragile to scrape.

Two formats in the wild - subject prefix `BA e-ticket receipt` on
older mail and `Your e-ticket receipt` on more recent mail.

Modern format (per segment):

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

Legacy format (per segment, ~2013):

    Flight number:       BA2762
    From:                Gatwick (London) Terminal N
    To:                  Amsterdam
    Depart:              16 May 2013 16:00
    Arrive:              16 May 2013 18:10
    Cabin:               Euro Traveller
    Operated by:         British Airways
    Booking status:      Confirmed

Each `BAnnnn` segment becomes one `FlightReservation` sharing the
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

from mailsift_extractor import read_message

BOOKING_RE = re.compile(
    r"(?:British Airways )?booking reference(?: is)?:?\s*([A-Z0-9]{5,8})",
    re.IGNORECASE,
)
# Modern format: `BAnnnn: British Airways | ...` header line, then
# `Depart:`/`Arrive:` lines with `date time - place`.
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

# Legacy format: label/value pairs. Values are padded with spaces to
# align the column, then trimmed. `From:`/`To:` carry the airport
# phrase directly; `Depart:`/`Arrive:` carry the same
# `date time` split as the modern format but without the trailing
# ` - place` (which appears on `From:`/`To:` instead).
LEGACY_FLIGHT_RE = re.compile(r"^Flight number:\s+(BA\d{2,4})\s*$", re.MULTILINE)
LEGACY_FROM_RE = re.compile(r"^From:\s+(.+?)\s*$", re.MULTILINE)
LEGACY_TO_RE = re.compile(r"^To:\s+(.+?)\s*$", re.MULTILINE)
LEGACY_DEPART_RE = re.compile(
    r"^Depart:\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+(\d{1,2}:\d{2})\s*$",
    re.MULTILINE,
)
LEGACY_ARRIVE_RE = re.compile(
    r"^Arrive:\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+(\d{1,2}:\d{2})\s*$",
    re.MULTILINE,
)


def parse_naive_dt(date_str: str, time_str: str) -> datetime | None:
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%d %b %Y %H:%M")
    except ValueError:
        return None


def airport_from_phrase(phrase: str) -> dict:
    """Turn a BA airport phrase into an Airport object.

    Modern format uses ` - ` to separate the terminal:
        `Heathrow (London) - Terminal 5`
    Legacy format inlines it after the parenthesised city:
        `Gatwick (London) Terminal N`
    Plain form (no city, no terminal) also works:
        `Amsterdam`
    """
    text = phrase.strip()
    terminal = None
    if " - " in text:
        text, terminal = text.split(" - ", 1)
        terminal = terminal.strip()
    name = text.strip()
    address = None
    # Split off `(city)` and anything trailing it (the legacy
    # `Terminal N` after the paren).
    m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*(.*)$", name)
    if m:
        name = m.group(1).strip()
        address = m.group(2).strip()
        trailing = m.group(3).strip()
        if trailing and not terminal:
            terminal = trailing
    out: dict = {"@type": "Airport", "name": name}
    if address:
        out["address"] = address
    if terminal:
        out["alternateName"] = terminal
    return out


def parse_modern_segments(text: str) -> list[tuple]:
    """Return `(flight_no, dep_dt, arr_dt, dep_phrase, arr_phrase)` per
    segment for the modern itinerary layout, or `[]` if this text
    doesn't match.
    """
    headers = list(SEGMENT_RE.finditer(text))
    out = []
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
        out.append((flight_no, dep_dt, arr_dt, dep_match.group(3), arr_match.group(3)))
    return out


def parse_legacy_segments(text: str) -> list[tuple]:
    """Return the same tuple as `parse_modern_segments`, for the ~2013
    label/value layout.

    Segments are delimited by `Flight number:` headers. The four
    label lines that make up a segment (`From:`, `To:`, `Depart:`,
    `Arrive:`) appear in a fixed order within that block; the block
    ends at the next `Flight number:` or the end of the itinerary
    section.
    """
    headers = list(LEGACY_FLIGHT_RE.finditer(text))
    out = []
    for index, header in enumerate(headers):
        flight_no = header.group(1)
        block_start = header.end()
        block_end = (
            headers[index + 1].start() if index + 1 < len(headers) else len(text)
        )
        block = text[block_start:block_end]
        from_m = LEGACY_FROM_RE.search(block)
        to_m = LEGACY_TO_RE.search(block)
        dep_m = LEGACY_DEPART_RE.search(block)
        arr_m = LEGACY_ARRIVE_RE.search(block)
        if not (from_m and to_m and dep_m and arr_m):
            continue
        dep_dt = parse_naive_dt(dep_m.group(1), dep_m.group(2))
        arr_dt = parse_naive_dt(arr_m.group(1), arr_m.group(2))
        if dep_dt is None or arr_dt is None:
            continue
        out.append((flight_no, dep_dt, arr_dt, from_m.group(1), to_m.group(1)))
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

    segments = parse_modern_segments(text) or parse_legacy_segments(text)
    if not segments:
        return 0

    for flight_no, dep_dt, arr_dt, dep_phrase, arr_phrase in segments:
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
                "departureAirport": airport_from_phrase(dep_phrase),
                "arrivalAirport": airport_from_phrase(arr_phrase),
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
