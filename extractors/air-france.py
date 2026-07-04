#!/usr/bin/env python3
"""Air France booking confirmations.

Sent from `admin@service-airfrance.com` with subject
`Booking confirmed - <origin>-<destination> on DD/MM/YYYY`. The HTML
body lists each flight segment between a `<origin> (IATA) - <dest>
(IATA)` route header and the next, in this shape:

    Saturday, December 30
    18h05 Hamburg Airport - Terminal 1
    Flight AF1511 - Operated by Air France
    19h45 Aeroport Charles de Gaulle - Terminal 2F

The year is not in the per-segment block - it's only in the subject's
`on DD/MM/YYYY` field, so we read it from there.
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


SUBJECT_DATE_RE = re.compile(r"on\s+(\d{1,2}/\d{1,2}/\d{4})\s*$", re.I)
BOOKING_RE = re.compile(r"Booking reference\s*\n+\s*([A-Z0-9]{5,8})")
SEGMENT_HEADER_RE = re.compile(
    r"^(?P<from_city>[A-Z][\w .'-]+?)\s*\((?P<from_iata>[A-Z]{3})\)\s*-\s*"
    r"(?P<to_city>[A-Z][\w .'-]+?)\s*\((?P<to_iata>[A-Z]{3})\)\s*$",
    re.MULTILINE,
)
DATE_LINE_RE = re.compile(r"^[A-Z][a-z]+,\s+([A-Z][a-z]+)\s+(\d{1,2})\s*$")
TIME_AIRPORT_RE = re.compile(r"^(\d{1,2})h(\d{2})\s+(.+?)\s*$")
FLIGHT_RE = re.compile(r"Flight\s+([A-Z]{2})(\d{2,4})\b")


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


def split_airport(phrase: str) -> tuple[str, str | None]:
    """Split "Hamburg Airport - Terminal 1" into (name, terminal)."""
    if " - " in phrase:
        name, terminal = phrase.split(" - ", 1)
        return name.strip(), terminal.strip()
    return phrase.strip(), None


def parse_seg_dt(
    month_name: str, day: str, year: int, hh: str, mm: str
) -> datetime | None:
    try:
        return datetime.strptime(
            f"{day} {month_name} {year} {hh}:{mm}", "%d %B %Y %H:%M"
        )
    except ValueError:
        return None


def main() -> int:
    mail = read_message()
    if not mail.html or not mail.subject:
        return 0

    subject_match = SUBJECT_DATE_RE.search(mail.subject)
    if not subject_match:
        return 0
    # Subject's date uses the recipient's locale day/month order, but
    # Air France writes US-style mm/dd/yyyy in English mails. We only
    # need the year, so the ambiguity doesn't matter here.
    booking_year = int(subject_match.group(1).split("/")[-1])

    text = strip_html(mail.html)

    booking_match = BOOKING_RE.search(text)
    if not booking_match:
        return 0
    booking = booking_match.group(1)

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    # Index of each segment header gives us the route + the start of
    # that segment's per-flight block.
    segment_starts = [
        (i, match)
        for i, match in (
            (i, SEGMENT_HEADER_RE.match(lines[i])) for i in range(len(lines))
        )
        if match
    ]
    if not segment_starts:
        return 0

    for index, (start_i, header) in enumerate(segment_starts):
        end_i = (
            segment_starts[index + 1][0]
            if index + 1 < len(segment_starts)
            else len(lines)
        )
        block = lines[start_i + 1 : end_i]

        # Within this block, walk forward and grab:
        #   1. the date line ("Saturday, December 30")
        #   2. first time+airport line (depart)
        #   3. flight number line
        #   4. next time+airport line (arrive)
        date_match = None
        dep_match = None
        flight_match = None
        arr_match = None
        for line in block:
            if date_match is None:
                m = DATE_LINE_RE.match(line)
                if m:
                    date_match = m
                    continue
            if date_match and dep_match is None:
                m = TIME_AIRPORT_RE.match(line)
                if m:
                    dep_match = m
                    continue
            if dep_match and flight_match is None:
                m = FLIGHT_RE.search(line)
                if m:
                    flight_match = m
                    continue
            if flight_match and arr_match is None:
                m = TIME_AIRPORT_RE.match(line)
                if m:
                    arr_match = m
                    break

        if not (date_match and dep_match and flight_match and arr_match):
            continue

        dep_dt = parse_seg_dt(
            date_match.group(1),
            date_match.group(2),
            booking_year,
            dep_match.group(1),
            dep_match.group(2),
        )
        arr_dt = parse_seg_dt(
            date_match.group(1),
            date_match.group(2),
            booking_year,
            arr_match.group(1),
            arr_match.group(2),
        )
        if dep_dt is None or arr_dt is None:
            continue
        if arr_dt < dep_dt:
            # Overnight flight: arrival is next day.
            arr_dt = arr_dt.replace(day=arr_dt.day + 1)

        dep_name, dep_terminal = split_airport(dep_match.group(3))
        arr_name, arr_terminal = split_airport(arr_match.group(3))

        airline_code = flight_match.group(1)
        flight_num = flight_match.group(2)
        airline_name = {"AF": "Air France", "KL": "KLM Royal Dutch Airlines"}.get(
            airline_code, airline_code
        )

        dep_airport: dict = {
            "@type": "Airport",
            "name": dep_name,
            "iataCode": header.group("from_iata"),
            "address": header.group("from_city").strip(),
        }
        if dep_terminal:
            dep_airport["alternateName"] = dep_terminal
        arr_airport: dict = {
            "@type": "Airport",
            "name": arr_name,
            "iataCode": header.group("to_iata"),
            "address": header.group("to_city").strip(),
        }
        if arr_terminal:
            arr_airport["alternateName"] = arr_terminal

        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": booking,
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": flight_num.lstrip("0") or "0",
                "airline": {
                    "@type": "Airline",
                    "iataCode": airline_code,
                    "name": airline_name,
                },
                "departureAirport": dep_airport,
                "arrivalAirport": arr_airport,
                "departureTime": dep_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "arrivalTime": arr_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        Path(f"af-{booking}-{airline_code}{flight_num}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
