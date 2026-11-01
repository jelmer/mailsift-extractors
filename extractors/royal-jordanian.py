#!/usr/bin/env python3
"""Royal Jordanian booking mail from `rj.com`, 2013-2014.

All three templates are sent through Amadeus and carry the same
booking reference, so they emit the same filenames per flight and a
later mail replaces an earlier one:

- `Confirmation for reservation <Surname>, <City>, <day> <Mon>.` from
  `ibesupport@rj.com`, sent when booking on rj.com.
- `Acknowledgment for schedule changes for reservation ...`, the
  same HTML template sent after a retime.
- `SURNAME/GIVEN MR 09JAN HKG AMM` from `res-support@rj.com`, the
  plain-text Amadeus "Passenger itinerary receipt".

The HTML templates flatten (via `strip_html(block_tags=True)`) into
one block per flight:

    Flight 1
    Thursday, January 09, 2014
    confirmed
    Departure:
    21:25
    Hong Kong, Hong Kong (SAR of China) - Hong Kong International, terminal 1
    Arrival:
    06:15
    +1
    day(s)
    Amman, Jordan - Queen Alia
    ...
    Airline:
    Royal Jordanian RJ183

The receipt is a fixed-width table without years or arrival dates:

     HONG KONG       RJ 183  Q  09JAN  2125     QLANHKG1  ...
     TERMINAL:1         FLIGHT OPERATED BY:   ROYAL JORDANIAN
     AMMAN                            ARRIVAL TIME: 0615

The year comes from the receipt's issue date, and an arrival time
earlier than the departure time is taken to mean the next day.

None of this mail is DKIM-signed (and SPF fails, as Amadeus relays
it), so the manifest only lets unsigned mail through if it was
received before 2016.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import Mail, read_message, strip_html

HTML_SUBJECT_RE = re.compile(
    r"^(?:Confirmation|Acknowledgment for schedule changes) for reservation ",
    re.IGNORECASE,
)
# "SURNAME/GIVEN MR 09JAN HKG AMM": passenger, first departure date,
# then the first leg's origin and destination.
RECEIPT_SUBJECT_RE = re.compile(
    r"^[A-Z' -]+/[A-Z' -]+ \d{2}[A-Z]{3} [A-Z]{3} [A-Z]{3}\s*$"
)

BOOKING_RE = re.compile(r"^Booking reservation number:\s*(?P<ref>[A-Z0-9]{5,8})$")
ETICKET_RE = re.compile(r"^E-ticket number (?P<number>[\d-]+):$")
FLIGHT_HEADER_RE = re.compile(r"^Flight \d+$")
LONG_DATE_RE = re.compile(r"^[A-Za-z]+, (?P<date>[A-Za-z]+ \d{1,2}, \d{4})$")
TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
DAY_OFFSET_RE = re.compile(r"^\+(?P<days>\d+)$")
FLIGHT_NUMBER_RE = re.compile(
    r"^(?P<name>.+) (?P<airline>[A-Z0-9]{2})(?P<number>\d{1,4})$"
)
TERMINAL_RE = re.compile(r",\s*terminal (?P<terminal>\S+)$", re.IGNORECASE)

RECEIPT_ISSUED_RE = re.compile(r"\bDATE: (?P<date>\d{1,2} [A-Z]{3} \d{4})\b")
RECEIPT_NAME_RE = re.compile(
    r"\bNAME: (?P<surname>[^/\n]+)/(?P<given>[^\n]+?)\s*$", re.MULTILINE
)
RECEIPT_TICKET_RE = re.compile(
    r"^ TICKET NUMBER\s+: ETKT (?P<number>[\d ]+?)\s*$", re.MULTILINE
)
RECEIPT_BOOKING_RE = re.compile(
    r"^ BOOKING REF :.*?AIRLINE: [A-Z0-9]{2}/(?P<ref>[A-Z0-9]{5,8})\b", re.MULTILINE
)
RECEIPT_SEGMENT_RE = re.compile(
    r"^ (?P<origin>[A-Z][A-Z .'-]*?)\s{2,}"
    r"(?P<airline>[A-Z0-9]{2}) (?P<number>\d{1,4})\s+"
    r"(?P<booking_class>[A-Z])\s+(?P<date>\d{2}[A-Z]{3})\s+(?P<dep>\d{4})\s"
)
RECEIPT_TERMINAL_RE = re.compile(r"^ TERMINAL:(?P<terminal>\S+)")
RECEIPT_ARRIVAL_RE = re.compile(
    r"^ (?P<destination>[A-Z][A-Z .'-]*?)\s{2,}ARRIVAL TIME: (?P<arr>\d{4})\s*$"
)
_TITLES = {"MR", "MRS", "MS", "MISS", "MSTR", "DR"}

_PENDING_CONTEXT = {
    "@vocab": "https://schema.org/",
    "pending": "https://pending.schema.org/",
}


def _airline(code: str) -> dict:
    out = {"@type": "Airline", "iataCode": code}
    if code == "RJ":
        out["name"] = "Royal Jordanian"
    return out


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _write(booking: str, reservation: dict) -> None:
    flight = reservation["reservationFor"]
    code = flight["airline"]["iataCode"] + flight["flightNumber"]
    Path(f"rj-{booking}-{code}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )


def _html_airport(line: str) -> dict:
    """Parse `City, Country - Airport name[, terminal N]`."""
    place, sep, name = line.partition(" - ")
    if not sep:
        raise ValueError(f"expected 'City, Country - Airport', got {line!r}")
    city, _, country = place.partition(", ")
    terminal = TERMINAL_RE.search(name)
    if terminal:
        name = name[: terminal.start()]
    airport: dict = {"@type": "Airport", "name": name.strip()}
    if terminal:
        airport["alternateName"] = f"Terminal {terminal.group('terminal')}"
    address = {"@type": "PostalAddress", "addressLocality": city.strip()}
    if country.strip():
        address["addressCountry"] = country.strip()
    airport["address"] = address
    return airport


def _value_after(block: list[str], label: str) -> int:
    try:
        return block.index(label) + 1
    except ValueError:
        raise ValueError(f"no {label!r} in flight block {block[:2]!r}") from None


def _html_segment(block: list[str]) -> dict:
    date_m = LONG_DATE_RE.match(block[1]) if len(block) > 1 else None
    if not date_m:
        raise ValueError(f"expected flight date after {block[0]!r}")
    day = datetime.strptime(date_m.group("date"), "%B %d, %Y")

    dep = _value_after(block, "Departure:")
    arr = _value_after(block, "Arrival:")
    for i in (dep, arr):
        if not TIME_RE.match(block[i]):
            raise ValueError(f"expected HH:MM, got {block[i]!r}")
    dep_dt = datetime.combine(day, datetime.strptime(block[dep], "%H:%M").time())
    arr_dt = datetime.combine(day, datetime.strptime(block[arr], "%H:%M").time())
    arr_airport = arr + 1
    if m := DAY_OFFSET_RE.match(block[arr_airport]):
        arr_dt += timedelta(days=int(m.group("days")))
        arr_airport += 1
        if block[arr_airport] == "day(s)":
            arr_airport += 1

    airline = _value_after(block, "Airline:")
    flight_m = FLIGHT_NUMBER_RE.match(block[airline])
    if not flight_m:
        raise ValueError(f"unexpected airline line {block[airline]!r}")

    return {
        "@type": "Flight",
        "flightNumber": flight_m.group("number"),
        "airline": {
            "@type": "Airline",
            "iataCode": flight_m.group("airline"),
            "name": flight_m.group("name"),
        },
        "departureAirport": _html_airport(block[dep + 1]),
        "arrivalAirport": _html_airport(block[arr_airport]),
        "departureTime": _fmt(dep_dt),
        "arrivalTime": _fmt(arr_dt),
    }


def extract_html(mail: Mail) -> int:
    if not mail.html:
        return 0
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).split("\n")
        if line.strip()
    ]

    booking = None
    tickets: list[tuple[str, str]] = []
    for i, line in enumerate(lines):
        if m := BOOKING_RE.match(line):
            booking = m.group("ref")
        elif (m := ETICKET_RE.match(line)) and i + 2 < len(lines):
            # Followed by the ticket's route, then the passenger name.
            tickets.append((m.group("number"), lines[i + 2]))
    if booking is None:
        raise SystemExit("royal-jordanian: no booking reservation number")

    headers = [i for i, line in enumerate(lines) if FLIGHT_HEADER_RE.match(line)]
    if not headers:
        raise SystemExit("royal-jordanian: no flights in itinerary")
    # The special-requests table further down repeats "Flight N:" with
    # a colon, which FLIGHT_HEADER_RE doesn't match; the itinerary ends
    # at the payment section.
    try:
        end = lines.index("Flight payment and ticket")
    except ValueError:
        end = len(lines)

    for index, start in enumerate(headers):
        stop = headers[index + 1] if index + 1 < len(headers) else end
        try:
            flight = _html_segment(lines[start:stop])
        except ValueError as exc:
            raise SystemExit(f"royal-jordanian: {exc}") from exc
        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "FlightReservation",
            "reservationNumber": booking,
            "reservationFor": flight,
        }
        if len(tickets) == 1:
            reservation["ticketNumber"] = tickets[0][0]
            reservation["underName"] = {"@type": "Person", "name": tickets[0][1]}
        elif tickets:
            reservation["underName"] = [
                {"@type": "Person", "name": name} for _, name in tickets
            ]
        _write(booking, reservation)
    return 0


def _receipt_name(surname: str, given: str) -> str:
    words = given.split()
    if words and words[-1] in _TITLES:
        words = words[:-1]
    return " ".join([*words, surname.strip()])


def extract_receipt(mail: Mail) -> int:
    text = mail.text
    if not text:
        return 0
    text = text.replace("\r\n", "\n")

    booking_m = RECEIPT_BOOKING_RE.search(text)
    issued_m = RECEIPT_ISSUED_RE.search(text)
    if not booking_m or not issued_m:
        raise SystemExit("royal-jordanian: receipt without booking ref or issue date")
    booking = booking_m.group("ref")
    issued = datetime.strptime(issued_m.group("date"), "%d %b %Y").date()
    name_m = RECEIPT_NAME_RE.search(text)
    ticket_m = RECEIPT_TICKET_RE.search(text)

    lines = text.split("\n")
    found = False
    for i, line in enumerate(lines):
        seg = RECEIPT_SEGMENT_RE.match(line)
        if not seg:
            continue
        found = True
        terminal = None
        arrival = None
        for following in lines[i + 1 : i + 4]:
            if m := RECEIPT_TERMINAL_RE.match(following):
                terminal = m.group("terminal")
            elif m := RECEIPT_ARRIVAL_RE.match(following):
                arrival = m
                break
        if arrival is None:
            raise SystemExit(f"royal-jordanian: no arrival for {line.strip()!r}")

        day = datetime.strptime(f"{seg.group('date')} {issued.year}", "%d%b %Y").date()
        if day < issued:
            day = date(day.year + 1, day.month, day.day)
        dep_dt = datetime.combine(
            day, datetime.strptime(seg.group("dep"), "%H%M").time()
        )
        arr_dt = datetime.combine(
            day, datetime.strptime(arrival.group("arr"), "%H%M").time()
        )
        if arr_dt < dep_dt:
            arr_dt += timedelta(days=1)

        dep_airport: dict = {"@type": "Airport", "name": seg.group("origin").title()}
        if terminal:
            dep_airport["alternateName"] = f"Terminal {terminal}"
        flight = {
            "@type": "Flight",
            "flightNumber": seg.group("number"),
            "airline": _airline(seg.group("airline")),
            "departureAirport": dep_airport,
            "arrivalAirport": {
                "@type": "Airport",
                "name": arrival.group("destination").title(),
            },
            "departureTime": _fmt(dep_dt),
            "arrivalTime": _fmt(arr_dt),
            "pending:bookingClass": seg.group("booking_class"),
        }
        reservation: dict = {
            "@context": _PENDING_CONTEXT,
            "@type": "FlightReservation",
            "reservationNumber": booking,
            "reservationFor": flight,
        }
        if ticket_m:
            reservation["ticketNumber"] = ticket_m.group("number").replace(" ", "-")
        if name_m:
            reservation["underName"] = {
                "@type": "Person",
                "name": _receipt_name(name_m.group("surname"), name_m.group("given")),
            }
        _write(booking, reservation)
    if not found:
        raise SystemExit("royal-jordanian: no flights in receipt")
    return 0


def main() -> int:
    mail = read_message()
    subject = mail.subject or ""
    if HTML_SUBJECT_RE.match(subject):
        return extract_html(mail)
    if RECEIPT_SUBJECT_RE.match(subject):
        return extract_receipt(mail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
