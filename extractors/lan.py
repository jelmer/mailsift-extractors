#!/usr/bin/env python3
"""LAN Airlines (now LATAM) mail from `lan.com`, 2014-2018.

Two templates carry flight details:

- `E-Ticket Confirmation`, sent from a per-country address such as
  `sales@bo.lan.com` after purchase. The HTML itinerary flattens (via
  `strip_html(block_tags=True)`) into one block per flight:

      Wednesday 07 january 2015
      13:15
      Juliaca (JUL)
      14:55
      Lima (LIM)
      LA2096
      Operated by Lan Peru
      Economy-L

  The arrival has no date of its own; an arrival time earlier than
  the departure time is taken to mean the next day.

- `Boarding Pass of <NAME>. 15 december 2018 El Calafate - Buenos
  Aires LA 7735` from `checkinweb@lan.com`. The body is boilerplate
  and the boarding pass is an attached PDF, so the reservation is
  built from the subject alone: a date without a time, city names
  without IATA codes and no booking reference. The PDF is kept as a
  `.ticket.pdf`.

LAN didn't DKIM-sign any of this, so the manifest can't require it.
Instead the script refuses mail dated on or after `_CUTOFF`: genuine
mail from these templates is older, and a spoofer today can't reach
the unauthenticated path.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import Mail, read_message, strip_html

_CUTOFF = datetime(2019, 1, 1)

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

ETICKET_SUBJECT_RE = re.compile(r"^E-Ticket Confirmation\s*$", re.IGNORECASE)
BOARDING_PASS_SUBJECT_RE = re.compile(
    r"^Boarding Pass of (?P<name>.+?)\.\s+"
    r"(?P<day>\d{1,2}) (?P<month>[a-z]+) (?P<year>\d{4})\s+"
    r"(?P<origin>.+?) - (?P<destination>.+?)\s+"
    r"(?P<airline>[A-Z0-9]{2}) ?(?P<number>\d{1,4})\s*$",
    re.IGNORECASE,
)

BOOKING_LABEL = "Your reservation code is:"
BOOKING_RE = re.compile(r"^[A-Z0-9]{6}$")
PASSENGERS_RE = re.compile(r"^Passengers(?P<name>.*)$")
DATE_RE = re.compile(
    r"^[A-Za-z]+ (?P<day>\d{1,2}) (?P<month>[A-Za-z]+) (?P<year>\d{4})$"
)
TIME_RE = re.compile(r"^(?P<hh>\d{1,2}):(?P<mm>\d{2})$")
AIRPORT_RE = re.compile(r"^(?P<city>.+?) \((?P<iata>[A-Z]{3})\)$")
FLIGHT_RE = re.compile(r"^(?P<airline>[A-Z0-9]{2})(?P<number>\d{1,4})$")
# "Economy-L": cabin, then the booking class letter.
CABIN_RE = re.compile(r"^(?P<cabin>[A-Za-z ]+)-(?P<booking_class>[A-Z])$")

_PENDING_CONTEXT = {
    "@vocab": "https://schema.org/",
    "pending": "https://pending.schema.org/",
}


def _month(name: str) -> int:
    try:
        return _MONTHS[name.lower()]
    except KeyError:
        raise ValueError(f"unknown month name {name!r}") from None


def _airline(code: str) -> dict:
    out = {"@type": "Airline", "iataCode": code}
    if code == "LA":
        out["name"] = "LAN Airlines"
    return out


def _airport(line: str) -> dict:
    m = AIRPORT_RE.match(line)
    if not m:
        raise ValueError(f"expected 'City (IATA)', got {line!r}")
    return {"@type": "Airport", "name": m.group("city"), "iataCode": m.group("iata")}


def _time(line: str) -> tuple[int, int]:
    m = TIME_RE.match(line)
    if not m:
        raise ValueError(f"expected HH:MM, got {line!r}")
    return int(m.group("hh")), int(m.group("mm"))


def _eticket_segment(lines: list[str], i: int) -> dict:
    """Parse the itinerary block whose flight number is on `lines[i]`.

    The five lines before it are date, departure time, departure
    airport, arrival time and arrival airport; the cabin follows,
    possibly after an `Operated by` line.
    """
    if i < 5:
        raise ValueError(f"flight number {lines[i]!r} without itinerary block")
    date_m = DATE_RE.match(lines[i - 5])
    if not date_m:
        raise ValueError(f"expected itinerary date, got {lines[i - 5]!r}")
    day = date(
        int(date_m.group("year")),
        _month(date_m.group("month")),
        int(date_m.group("day")),
    )
    dep_dt = datetime(day.year, day.month, day.day, *_time(lines[i - 4]))
    arr_dt = datetime(day.year, day.month, day.day, *_time(lines[i - 2]))
    if arr_dt < dep_dt:
        arr_dt += timedelta(days=1)

    flight_m = FLIGHT_RE.match(lines[i])
    assert flight_m is not None
    flight: dict = {
        "@type": "Flight",
        "flightNumber": flight_m.group("number"),
        "airline": _airline(flight_m.group("airline")),
        "departureAirport": _airport(lines[i - 3]),
        "arrivalAirport": _airport(lines[i - 1]),
        "departureTime": dep_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "arrivalTime": arr_dt.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    for line in lines[i + 1 : i + 3]:
        if m := CABIN_RE.match(line):
            flight["pending:cabinClass"] = m.group("cabin").strip()
            flight["pending:bookingClass"] = m.group("booking_class")
            break
    return flight


def extract_eticket(mail: Mail) -> int:
    if not mail.html:
        return 0
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).split("\n")
        if line.strip()
    ]

    try:
        label = lines.index(BOOKING_LABEL)
    except ValueError:
        raise SystemExit("lan: no reservation code in e-ticket confirmation") from None
    booking = lines[label + 1] if label + 1 < len(lines) else ""
    if not BOOKING_RE.match(booking):
        raise SystemExit(f"lan: unexpected reservation code {booking!r}")

    passengers: list[str] = []
    for index, line in enumerate(lines):
        if m := PASSENGERS_RE.match(line):
            first = m.group("name").strip()
            if first:
                passengers.append(first)
            for following in lines[index + 1 :]:
                if following.startswith("Total Fare"):
                    break
                passengers.append(following)
            break

    try:
        itinerary = lines.index("Itinerary")
    except ValueError:
        raise SystemExit("lan: no itinerary in e-ticket confirmation") from None
    flight_lines = [
        i for i, line in enumerate(lines) if i > itinerary and FLIGHT_RE.match(line)
    ]
    if not flight_lines:
        raise SystemExit("lan: no flights in e-ticket confirmation")

    for i in flight_lines:
        try:
            flight = _eticket_segment(lines, i)
        except ValueError as exc:
            raise SystemExit(f"lan: {exc}") from exc
        reservation: dict = {
            "@context": _PENDING_CONTEXT
            if "pending:cabinClass" in flight
            else "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": booking,
            "reservationFor": flight,
        }
        people = [{"@type": "Person", "name": name} for name in passengers]
        if len(people) == 1:
            reservation["underName"] = people[0]
        elif people:
            reservation["underName"] = people
        code = flight["airline"]["iataCode"] + flight["flightNumber"]
        Path(f"lan-{booking}-{code}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


def extract_boarding_pass(mail: Mail, subject: re.Match[str]) -> int:
    try:
        day = date(
            int(subject.group("year")),
            _month(subject.group("month")),
            int(subject.group("day")),
        )
    except ValueError as exc:
        raise SystemExit(f"lan: bad boarding pass date: {exc}") from exc

    airline = subject.group("airline").upper()
    number = subject.group("number")
    # TODO(jelmer): The attached PDF carries the departure time, the
    # IATA codes and the ticket number; read those once there is a
    # PDF text extraction helper.
    reservation = {
        "@context": "https://schema.org",
        "@type": "FlightReservation",
        "underName": {"@type": "Person", "name": subject.group("name").strip()},
        "reservationFor": {
            "@type": "Flight",
            "flightNumber": number,
            "airline": _airline(airline),
            "departureAirport": {
                "@type": "Airport",
                "name": subject.group("origin").strip(),
            },
            "arrivalAirport": {
                "@type": "Airport",
                "name": subject.group("destination").strip(),
            },
            "departureTime": day.isoformat(),
        },
    }
    slug = f"lan-{airline}{number}-{day.strftime('%Y%m%d')}"
    Path(f"{slug}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    pdf = mail.find_pdf_attachment()
    if pdf is not None:
        Path(f"{slug}.ticket.pdf").write_bytes(pdf.bytes)
    return 0


def main() -> int:
    mail = read_message()
    if mail.date is not None and mail.date.replace(tzinfo=None) >= _CUTOFF:
        return 0
    subject = mail.subject or ""
    if ETICKET_SUBJECT_RE.match(subject):
        return extract_eticket(mail)
    if m := BOARDING_PASS_SUBJECT_RE.match(subject):
        return extract_boarding_pass(mail, m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
