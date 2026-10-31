#!/usr/bin/env python3
"""KLM Royal Dutch Airlines booking confirmations.

Sent from `noreply@klm.com` with subject `Confirmation: <route>
(<booking-code>)`. The HTML body has no schema.org markup but lists
each flight segment in a consistent block:

    Tue 19 Feb 19
    06:30 London (Heathrow Airport, United Kingdom)
    Tue 19 Feb 19
    09:00 Amsterdam (Schiphol, Netherlands)
    Class: Business
    Flight number: KL 1000

After stripping HTML the blocks are paragraph-separated. We walk each
`Flight number: <CODE>` occurrence and reconstruct the segment by
reading the preceding four lines (depart date, depart time+airport,
arrive date, arrive time+airport).

The 2012-2019 templates put source newlines inside the table cell,
so the time, city and parenthesised airport arrive on separate
lines:

    Wed 17 Dec 14
    12:25
    Amsterdam
    (Schiphol, Netherlands)

Those are joined back into one `<time> <airport>` line first.

Booking code is in the subject; we also accept a `Booking code` /
`Booking - Booking code` header in the body as a fallback.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

SUBJECT_BOOKING_RE = re.compile(
    r"Confirmation:\s+.+?\s+\(([A-Z0-9]{5,8})\)\s*$", re.IGNORECASE
)
BODY_BOOKING_RE = re.compile(r"Booking code\s*\n+\s*([A-Z0-9]{5,8})\b")
FLIGHT_NUMBER_RE = re.compile(r"Flight number:\s*([A-Z]{2})\s*(\d{1,4})")
DATE_LINE_RE = re.compile(
    r"^(?P<wday>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+(?P<mon>[A-Z][a-z]{2})\s+(?P<yy>\d{2})\s*$"
)
TIME_AIRPORT_RE = re.compile(r"^(?P<time>\d{1,2}:\d{2})\s+(?P<airport>.+?)\s*$")
BARE_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
# "Class: <name>" sits between the arrival airport and the flight
# number; KLM writes both "Business" and "World Business Class".
CLASS_LINE_RE = re.compile(r"^Class:\s*(?P<cabin>.+?)\s*$")


def parse_naive_dt(
    wday: str, day: str, mon: str, yy: str, time: str
) -> datetime | None:
    # KLM uses two-digit years; treat them as 20YY.
    try:
        return datetime.strptime(f"{day} {mon} 20{yy} {time}", "%d %b %Y %H:%M")
    except ValueError:
        return None


def parse_airport(phrase: str) -> dict:
    """Pull airport name and parenthesised airport-info out of e.g.
    "London (Heathrow Airport, United Kingdom)".

    KLM puts the city outside the parens and "<airport name>,
    <country>" inside. Use the airport name as the schema `name` and
    keep the city as a label.
    """
    out: dict = {"@type": "Airport"}
    m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", phrase.strip())
    if m:
        out["name"] = m.group(2).split(",")[0].strip()
        out["address"] = m.group(1).strip()
    else:
        out["name"] = phrase.strip()
    return out


class LayoutError(ValueError):
    """The lines before a `Flight number:` don't form a segment."""


def join_split_times(lines: list[str]) -> list[str]:
    """Rejoin `<time>` / `<city>` / `(<airport>)` runs into one line."""
    out = []
    i = 0
    while i < len(lines):
        if (
            BARE_TIME_RE.match(lines[i])
            and i + 2 < len(lines)
            and lines[i + 2].startswith("(")
            and lines[i + 2].endswith(")")
        ):
            out.append(" ".join(lines[i : i + 3]))
            i += 3
        else:
            out.append(lines[i])
            i += 1
    return out


# What has to precede a `Flight number:` line, nearest first.
_SEGMENT_LINES = (
    ("arrival time and airport", TIME_AIRPORT_RE),
    ("arrival date", DATE_LINE_RE),
    ("departure time and airport", TIME_AIRPORT_RE),
    ("departure date", DATE_LINE_RE),
)


def segment_before(
    lines: list[str], index: int
) -> tuple[list[dict], str | None] | None:
    """Read the segment ending just above `lines[index]`.

    Returns the arrival time, arrival date, departure time and
    departure date match groups (in that order) plus the cabin from an
    optional `Class:` line directly above the flight number.

    Returns None if there is no time line above at all: the seat list
    further down repeats each `Flight number:` under a bare
    `<origin> - <destination>` heading. Raises `LayoutError` if a
    segment starts but doesn't have the expected shape.
    """
    cursor = index - 1
    cabin = None
    if cursor >= 0 and (c_match := CLASS_LINE_RE.match(lines[cursor])):
        cabin = c_match.group("cabin")
        cursor -= 1
    if cursor < 0 or not TIME_AIRPORT_RE.match(lines[cursor]):
        return None
    groups = []
    for what, regex in _SEGMENT_LINES:
        line = lines[cursor] if cursor >= 0 else None
        match = regex.match(line) if line is not None else None
        if match is None:
            raise LayoutError(
                f"expected {what} before {lines[index]!r}, found {line!r}"
            )
        groups.append(match.groupdict())
        cursor -= 1
    return groups, cabin


def extract(mail, max_message_date: datetime | None = None) -> int:
    """Emit one reservation per flight segment in `mail`.

    With `max_message_date` set, refuse mail whose `Date:` header is
    missing or on or after it. The legacy manifest uses this to accept
    unsigned mail from before KLM signed with DKIM.
    """
    if max_message_date is not None and (
        mail.date is None or mail.date.replace(tzinfo=None) >= max_message_date
    ):
        return 0

    if not mail.html:
        return 0

    booking = None
    if mail.subject and (m := SUBJECT_BOOKING_RE.search(mail.subject)):
        booking = m.group(1)

    text = strip_html(mail.html, block_tags=True)

    if booking is None:
        m = BODY_BOOKING_RE.search(text)
        if m:
            booking = m.group(1)
    if booking is None:
        return 0

    lines = join_split_times([ln.strip() for ln in text.split("\n") if ln.strip()])

    flight_lines = [
        (index, fn_match)
        for index, line in enumerate(lines)
        if (fn_match := FLIGHT_NUMBER_RE.match(line))
    ]
    segments = [
        (fn_match, segment)
        for index, fn_match in flight_lines
        if (segment := segment_before(lines, index)) is not None
    ]
    if flight_lines and not segments:
        raise LayoutError(
            f"no itinerary segment above any of {len(flight_lines)} flight numbers"
        )

    for fn_match, segment in segments:
        airline_code = fn_match.group(1)
        flight_num = fn_match.group(2)
        (arr_time_d, arr_date_d, dep_time_d, dep_date_d), cabin = segment
        dep_dt = parse_naive_dt(
            dep_date_d["wday"],
            dep_date_d["day"],
            dep_date_d["mon"],
            dep_date_d["yy"],
            dep_time_d["time"],
        )
        arr_dt = parse_naive_dt(
            arr_date_d["wday"],
            arr_date_d["day"],
            arr_date_d["mon"],
            arr_date_d["yy"],
            arr_time_d["time"],
        )
        if dep_dt is None or arr_dt is None:
            continue
        dep_airport = parse_airport(dep_time_d["airport"])
        arr_airport = parse_airport(arr_time_d["airport"])

        airline_name = {"KL": "KLM Royal Dutch Airlines", "AF": "Air France"}.get(
            airline_code, airline_code
        )
        flight: dict = {
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
        }
        # Cabin class lives under the pending.schema.org namespace.
        # An object @context so consumers can resolve the prefix.
        if cabin:
            flight["pending:cabinClass"] = cabin
            context: str | dict = {
                "@vocab": "https://schema.org/",
                "pending": "https://pending.schema.org/",
            }
        else:
            context = "https://schema.org"

        reservation: dict = {
            "@context": context,
            "@type": "FlightReservation",
            "reservationNumber": booking,
            "reservationFor": flight,
        }
        Path(f"klm-{booking}-{airline_code}{flight_num}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


def main() -> int:
    return extract(read_message())


if __name__ == "__main__":
    sys.exit(main())
