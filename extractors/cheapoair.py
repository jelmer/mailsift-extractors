#!/usr/bin/env python3
"""CheapOair flight booking receipts (2014 template).

CheapOair sends two mails per booking from `cheapoair@cheapoair.com`,
"AIR TICKET NUMBER & AIRLINE CONFIRMATION. Booking# <n>" and
"CheapOair.com - <Last>/ <First> - Booking receipt - Booking # <n>".
Both carry the same HTML body. Each flight sits under a trip heading
and flattens (via `strip_html(block_tags=True)`) into:

    Departing Flight - Saturday, Jan 03, 2015
    [airline:Z8]
    Linea Aerea Amaszonas
    Flight 501
    Canadair Regional  Jet
    Airline confirmation:
    ABCDEF
    Select Seats
    From
    Cuzco
    (CUZ)
    10:35am
    - Jan 03, Sat
    To
    La Paz
    (LPB)
    12:35pm
    - Jan 03, Sat

The airline's IATA code only appears in the logo URL
(`/I/AI/Z8.gif`), so the logo is rewritten into the `[airline:Z8]`
marker before flattening. The per-airport dates have no year; it
comes from the trip heading.

This mail is not DKIM-signed, so a message-date cutoff guards the
code path against present-day spoofs.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

# The template seen is from 2014. CheapOair's newer mail (from
# mycheapoair.com) is DKIM-signed, so anything later than this that
# still arrives unsigned in the old template is suspicious.
# TODO: add a DKIM-gated variant if a signed mail in this template
# turns up.
_CUTOFF = datetime(2017, 1, 1)

LOGO_RE = re.compile(
    r"<img\b[^>]*\bsrc=['\"][^'\"]*/I/AI/(?P<code>[A-Z0-9]{2})\.gif['\"][^>]*>",
    re.IGNORECASE,
)
MARKER_RE = re.compile(r"^\[airline:(?P<code>[A-Z0-9]{2})\]$")
HEADING_RE = re.compile(
    r"^\w+ Flight - [A-Za-z]+, (?P<month>[A-Za-z]{3}) (?P<day>\d{1,2}), (?P<year>\d{4})$"
)
FLIGHT_RE = re.compile(r"^Flight\s+(?P<number>\d{1,4})$")
IATA_RE = re.compile(r"^\((?P<iata>[A-Z]{3})\)$")
TIME_RE = re.compile(r"^(?P<time>\d{1,2}:\d{2}\s*[ap]m)$", re.IGNORECASE)
DAY_RE = re.compile(r"^-\s*(?P<month>[A-Za-z]{3}) (?P<day>\d{1,2}), [A-Za-z]{3}$")
TRAVELER_RE = re.compile(r"^(?P<last>[^,]+),\s*(?P<first>.+)$")
TICKET_RE = re.compile(r"^(?P<ticket>\d{13,14}) E-Ticket$")


def _lines(html: str) -> list[str]:
    html = LOGO_RE.sub(lambda m: f"<div>[airline:{m.group('code')}]</div>", html)
    text = strip_html(html, block_tags=True).replace("\xa0", " ")
    return [line.strip() for line in text.split("\n") if line.strip()]


def _value_after(lines: list[str], label: str) -> str | None:
    for i, line in enumerate(lines[:-1]):
        if line == label:
            return lines[i + 1]
    return None


def _travelers(lines: list[str]) -> list[tuple[str, str | None]]:
    """Read (name, ticket number) pairs from the "Traveler Name" table.

    Names are written "Last, First" followed by a "(Adult)" style
    marker; the ticket number cell follows.
    """
    try:
        start = lines.index("Special Request")
    except ValueError:
        return []
    out: list[tuple[str, str | None]] = []
    i = start + 1
    while i + 1 < len(lines) and lines[i + 1].startswith("("):
        m = TRAVELER_RE.match(lines[i])
        if not m:
            break
        name = f"{m.group('first').strip()} {m.group('last').strip()}"
        ticket_m = TICKET_RE.match(lines[i + 2]) if i + 2 < len(lines) else None
        out.append((name, ticket_m.group("ticket") if ticket_m else None))
        # Name, passenger type, ticket, meal, special request.
        i += 5
    return out


def _resolve(month: str, day: str, hhmm: str, not_before: datetime) -> datetime:
    """Build a datetime from a year-less date, choosing the first year
    that doesn't put it before `not_before`'s date (a Dec/Jan rollover).
    """
    for year in (not_before.year, not_before.year + 1):
        dt = datetime.strptime(f"{day} {month} {year} {hhmm}", "%d %b %Y %I:%M%p")
        if dt.date() >= not_before.date():
            return dt
    raise ValueError(f"cannot place {month} {day} after {not_before}")


def _segments(lines: list[str]) -> list[dict]:
    segments: list[dict] = []
    heading: datetime | None = None
    for i, line in enumerate(lines):
        if m := HEADING_RE.match(line):
            heading = datetime.strptime(
                f"{m.group('day')} {m.group('month')} {m.group('year')}", "%d %b %Y"
            )
            continue
        marker = MARKER_RE.match(line)
        if not marker:
            continue
        if heading is None:
            raise ValueError(f"flight block at line {i} has no trip heading")
        block = lines[i + 1 : i + 30]
        airline_name = block[0]
        flight_m = FLIGHT_RE.match(block[1])
        if not flight_m:
            raise ValueError(f"unexpected flight line {block[1]!r}")
        pnr = _value_after(block, "Airline confirmation:")
        ends = []
        for label in ("From", "To"):
            j = block.index(label)
            city, iata_line, time_line, day_line = block[j + 1 : j + 5]
            iata_m = IATA_RE.match(iata_line)
            time_m = TIME_RE.match(time_line)
            day_m = DAY_RE.match(day_line)
            if not (iata_m and time_m and day_m):
                raise ValueError(f"unexpected {label} block {block[j : j + 5]!r}")
            ends.append((city, iata_m.group("iata"), time_m.group("time"), day_m))
        (dep_city, dep_iata, dep_time, dep_day) = ends[0]
        (arr_city, arr_iata, arr_time, arr_day) = ends[1]
        dep = _resolve(dep_day.group("month"), dep_day.group("day"), dep_time, heading)
        arr = _resolve(arr_day.group("month"), arr_day.group("day"), arr_time, dep)
        segments.append(
            {
                "pnr": pnr,
                "flight": {
                    "@type": "Flight",
                    "flightNumber": flight_m.group("number").lstrip("0") or "0",
                    "airline": {
                        "@type": "Airline",
                        "iataCode": marker.group("code"),
                        "name": airline_name,
                    },
                    "departureAirport": {
                        "@type": "Airport",
                        "iataCode": dep_iata,
                        "address": {
                            "@type": "PostalAddress",
                            "addressLocality": dep_city,
                        },
                    },
                    "arrivalAirport": {
                        "@type": "Airport",
                        "iataCode": arr_iata,
                        "address": {
                            "@type": "PostalAddress",
                            "addressLocality": arr_city,
                        },
                    },
                    "departureTime": dep.strftime("%Y-%m-%dT%H:%M:%S"),
                    "arrivalTime": arr.strftime("%Y-%m-%dT%H:%M:%S"),
                },
            }
        )
    return segments


def main() -> int:
    mail = read_message()
    if mail.date is not None and mail.date.replace(tzinfo=None) >= _CUTOFF:
        return 0
    if not mail.html:
        return 0

    lines = _lines(mail.html)
    booking = _value_after(lines, "Booking #:")
    if not booking:
        return 0
    travelers = _travelers(lines)

    for segment in _segments(lines):
        flight = segment["flight"]
        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            # The airline's record locator is what check-in asks for;
            # fall back to CheapOair's own booking number.
            "reservationNumber": segment["pnr"] or booking,
            "broker": {"@type": "Organization", "name": "CheapOair"},
            "reservationFor": flight,
        }
        if len(travelers) == 1:
            name, ticket = travelers[0]
            reservation["underName"] = {"@type": "Person", "name": name}
            if ticket:
                reservation["ticketNumber"] = ticket
        elif travelers:
            reservation["underName"] = [
                {"@type": "Person", "name": name} for name, _ in travelers
            ]
        code = flight["airline"]["iataCode"]
        number = flight["flightNumber"]
        Path(f"cheapoair-{booking}-{code}{number}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
