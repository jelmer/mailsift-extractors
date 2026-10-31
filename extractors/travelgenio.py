#!/usr/bin/env python3
"""Travelgenio flight bookings.

Travelgenio sends two mails per booking, both without schema.org
markup:

- "Travelgenio - Booking" from `infort@corp.travelgenio.com`, sent in
  the customer's language (Dutch here) straight after booking, before
  payment and ticketing. Each segment flattens to

      Vertrek: Tan Son Nhut International (SGN), Ho Chi Minh City, ...
      Datum: 02/01/2014 - 18:30H
      Aankomst: Hong Kong International (HKG), Hong Kong, Hongkong
      21:55H
      Duur 01H 45m
      Vietnam Airlines (VN598)

  The arrival has a time but no date.

- "RESERVATION CONFIRMATION" from `mail@corp.travelgenio.com`, the
  e-ticket: a Travelport viewtrip itinerary in English. Each segment
  starts with `Flight` / `- Vietnam Airlines Corporation (VN) - 598`;
  the departure and arrival times are in ISO form in `title`
  attributes on the date and arrival-time spans.

Both carry the same Travelgenio record locator ("Uwreserveringscode",
"Reservation ID"), which is what we file under so the e-ticket
supersedes the earlier booking mail.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

BOOKING_CODE_RE = re.compile(r"Uw ?reserveringscode is (?P<code>[A-Z0-9]{5,8})\.")
BOOKING_SEGMENT_RE = re.compile(
    r"^Vertrek: (?P<dep_name>[^\n(]+?) \((?P<dep>[A-Z]{3})\), (?P<dep_city>[^,\n]+)[^\n]*\n"
    r"Datum: (?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4}) - (?P<dep_time>\d{1,2}:\d{2})H\n"
    r"Aankomst: (?P<arr_name>[^\n(]+?) \((?P<arr>[A-Z]{3})\), (?P<arr_city>[^,\n]+)[^\n]*\n"
    r"(?P<arr_time>\d{1,2}:\d{2})H\n"
    r"(?:Duur [^\n]+\n)?"
    r"(?P<airline>[^\n(]+?) \((?P<code>[A-Z0-9]{2})(?P<number>\d{1,4})\)$",
    re.MULTILINE,
)
BOOKING_PASSENGER_RE = re.compile(
    r"^Passagier \d+ - [^\n]*\nNaam:\s+(?P<given>[^\n]+?)\s+Achternaam:\s+(?P<family>[^\n]+)$",
    re.MULTILINE,
)

ETICKET_CODE_RE = re.compile(
    r"^Reservation ID:\n(?P<code>[A-Z0-9]{5,8})$", re.MULTILINE
)
ETICKET_TRAVELERS_RE = re.compile(
    r"^Travelers\n(?P<block>.*?)\nFlight$", re.MULTILINE | re.DOTALL
)
ETICKET_SEGMENT_RE = re.compile(
    r"^Flight\n- (?P<airline>[^\n]+?) \((?P<code>[A-Z0-9]{2})\) - (?P<number>\d{1,4})\n"
    r".*?^Depart:\n[^\n]+\n(?P<dep_block>.*?)\nArrive:\n[^\n]+\n(?P<arr_block>.*?)\nFlight\n"
    r".*?^Class of Service:\n(?P<cabin>[^\n(]+?) \((?P<booking_class>[A-Z])\)$"
    r"(?:\nStatus:\n(?P<status>[^\n(|]+))?",
    re.MULTILINE | re.DOTALL,
)
# "Tan Son Nhut Arpt (SGN),\nTerminal 2\nHo Chi Minh City": airport,
# optional terminal, optional city.
ETICKET_AIRPORT_RE = re.compile(
    r"^(?P<name>[^\n(]+?) \((?P<iata>[A-Z]{3})\),?\s*"
    r"(?:Terminal (?P<terminal>\S+)\s*)?(?P<city>[^\n]+)?$",
    re.DOTALL,
)
ISO_TITLE_RE = re.compile(r'title="(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"')


def airport(
    iata: str, name: str, city: str | None, terminal: str | None = None
) -> dict:
    out = {"@type": "Airport", "name": name.strip(), "iataCode": iata}
    if city:
        out["address"] = city.strip()
    if terminal:
        out["alternateName"] = f"Terminal {terminal}"
    return out


def flight(code: str, number: str, airline: str) -> dict:
    return {
        "@type": "Flight",
        "flightNumber": number,
        "airline": {"@type": "Airline", "iataCode": code, "name": airline.strip()},
    }


def people(names: list[str]) -> dict | list[dict]:
    out = [{"@type": "Person", "name": name} for name in names]
    return out[0] if len(out) == 1 else out


def booking_reservations(text: str) -> tuple[str, list[dict]] | None:
    code = BOOKING_CODE_RE.search(text)
    if not code:
        return None
    passengers = [
        f"{m.group('given')} {m.group('family')}"
        for m in BOOKING_PASSENGER_RE.finditer(text)
    ]
    out = []
    for seg in BOOKING_SEGMENT_RE.finditer(text):
        departure = datetime.strptime(
            f"{seg.group('year')}-{seg.group('month')}-{seg.group('day')} "
            f"{seg.group('dep_time')}",
            "%Y-%m-%d %H:%M",
        )
        arrival = datetime.combine(
            departure.date(), datetime.strptime(seg.group("arr_time"), "%H:%M").time()
        )
        # The arrival carries no date; a clock time before departure
        # means it lands the next day.
        if arrival < departure:
            arrival += timedelta(days=1)
        reservation_for = flight(
            seg.group("code"), seg.group("number"), seg.group("airline")
        )
        reservation_for.update(
            {
                "departureAirport": airport(
                    seg.group("dep"), seg.group("dep_name"), seg.group("dep_city")
                ),
                "arrivalAirport": airport(
                    seg.group("arr"), seg.group("arr_name"), seg.group("arr_city")
                ),
                "departureTime": departure.isoformat(),
                "arrivalTime": arrival.isoformat(),
            }
        )
        reservation: dict = {"reservationFor": reservation_for}
        if passengers:
            reservation["underName"] = people(passengers)
        out.append(reservation)
    return code.group("code"), out


def eticket_reservations(text: str, html: str) -> tuple[str, list[dict]] | None:
    code = ETICKET_CODE_RE.search(text)
    if not code:
        return None
    passengers: list[str] = []
    if travelers := ETICKET_TRAVELERS_RE.search(text):
        for line in travelers.group("block").split("\n"):
            family, _, given = line.partition(", ")
            name = f"{given} {family}" if given else family
            if name not in passengers:
                passengers.append(name)

    segments = list(ETICKET_SEGMENT_RE.finditer(text))
    times = ISO_TITLE_RE.findall(html)
    if len(times) != 2 * len(segments):
        raise ValueError(f"expected two timestamps per segment, got {times!r}")

    out = []
    for i, seg in enumerate(segments):
        dep = ETICKET_AIRPORT_RE.match(seg.group("dep_block"))
        arr = ETICKET_AIRPORT_RE.match(seg.group("arr_block"))
        if not dep or not arr:
            raise ValueError(f"unrecognised airports in segment: {seg.group(0)!r}")
        reservation_for = flight(
            seg.group("code"), seg.group("number"), seg.group("airline")
        )
        reservation_for.update(
            {
                "departureAirport": airport(
                    dep.group("iata"),
                    dep.group("name"),
                    dep.group("city"),
                    dep.group("terminal"),
                ),
                "arrivalAirport": airport(
                    arr.group("iata"),
                    arr.group("name"),
                    arr.group("city"),
                    arr.group("terminal"),
                ),
                "departureTime": times[2 * i],
                "arrivalTime": times[2 * i + 1],
                "pending:cabinClass": seg.group("cabin"),
                "pending:bookingClass": seg.group("booking_class"),
            }
        )
        reservation: dict = {"reservationFor": reservation_for}
        if (seg.group("status") or "").strip() == "Confirmed":
            reservation["reservationStatus"] = "https://schema.org/ReservationConfirmed"
        if passengers:
            reservation["underName"] = people(passengers)
        out.append(reservation)
    return code.group("code"), out


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    text = strip_html(mail.html, block_tags=True)
    text = "\n".join(line.strip() for line in text.split("\n") if line.strip())

    found = booking_reservations(text) or eticket_reservations(text, mail.html)
    if found is None:
        return 0
    code, reservations = found
    for reservation in reservations:
        reservation_for = reservation["reservationFor"]
        full = {
            "@context": {
                "@vocab": "https://schema.org/",
                "pending": "https://pending.schema.org/",
            },
            "@type": "FlightReservation",
            "reservationNumber": code,
            "broker": {"@type": "Organization", "name": "Travelgenio"},
            **reservation,
        }
        day = reservation_for["departureTime"][:10].replace("-", "")
        carrier = reservation_for["airline"]["iataCode"]
        slug = f"travelgenio-{code}-{day}-{carrier}{reservation_for['flightNumber']}"
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(full, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
