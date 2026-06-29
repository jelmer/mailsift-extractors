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

Booking code is in the subject; we also accept a `Booking code` /
`Booking - Booking code` header in the body as a fallback.
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


SUBJECT_BOOKING_RE = re.compile(r"Confirmation:\s+.+?\s+\(([A-Z0-9]{5,8})\)\s*$", re.I)
BODY_BOOKING_RE = re.compile(r"Booking code\s*\n+\s*([A-Z0-9]{5,8})\b")
FLIGHT_NUMBER_RE = re.compile(r"Flight number:\s*([A-Z]{2})\s*(\d{1,4})")
DATE_LINE_RE = re.compile(
    r"^(?P<wday>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+(?P<mon>[A-Z][a-z]{2})\s+(?P<yy>\d{2})\s*$"
)
TIME_AIRPORT_RE = re.compile(r"^(?P<time>\d{1,2}:\d{2})\s+(?P<airport>.+?)\s*$")


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


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    booking = None
    if mail.subject and (m := SUBJECT_BOOKING_RE.search(mail.subject)):
        booking = m.group(1)

    text = strip_html(mail.html)

    if booking is None:
        m = BODY_BOOKING_RE.search(text)
        if m:
            booking = m.group(1)
    if booking is None:
        return 0

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    # For each flight-number occurrence, walk back to find the most
    # recent four lines matching:
    #   <date>
    #   <time> <airport>
    #   <date>
    #   <time> <airport>
    for index, line in enumerate(lines):
        fn_match = FLIGHT_NUMBER_RE.match(line)
        if not fn_match:
            continue
        airline_code = fn_match.group(1)
        flight_num = fn_match.group(2)
        # Walk back from the flight-number line, collecting prior
        # lines that match either a date or a time+airport. Filler
        # lines (e.g. "Class: ..." which sits between the segment and
        # the flight number) are skipped. We stop once we have one
        # complete segment: [dep_date, dep_time_airport, arr_date,
        # arr_time_airport], i.e. four kept lines.
        cursor = index - 1
        collected: list[tuple[str, dict]] = []
        while cursor >= 0 and len(collected) < 4:
            current = lines[cursor]
            d_match = DATE_LINE_RE.match(current)
            t_match = TIME_AIRPORT_RE.match(current)
            if d_match:
                collected.append(("date", d_match.groupdict()))
            elif t_match:
                collected.append(("time", t_match.groupdict()))
            cursor -= 1
        if len(collected) < 4:
            continue
        # `collected` was built bottom-up, so the order is:
        #   [arr_time, arr_date, dep_time, dep_date]
        arr_time_d, arr_date_d, dep_time_d, dep_date_d = (
            entry[1] for entry in collected
        )
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
        Path(f"klm-{booking}-{airline_code}{flight_num}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
