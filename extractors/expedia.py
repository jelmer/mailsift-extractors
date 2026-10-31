#!/usr/bin/env python3
"""Expedia flight confirmations.

Two templates, both without schema.org markup:

- 2015-era "Expedia travel confirmation/e-Ticket" from
  `Confirmation@ExpediaConfirm.com`. Each leg starts with a
  `21 Feb 2015` / `-` / `Departure` header; each segment flattens to

      London
      Istanbul
      3 h 35 m
      STN
      13:10
      SAW
      18:45
      Pegasus Airlines 502
      Economy / Coach
      (V)

  The airline's IATA code only appears in the segment's logo URL
  (`images/airlines/smPC.GIF`). The airline record locators sit in a
  status box as `<airline>` / `<PNR>` pairs before `Expedia Booking ID`.

- 2017-era "Expedia travel confirmation" from `*.expediamail.com`.
  Legs start with `Departure` / `Thu., 1 Feb.` (no year) and segments
  look like

      China Southern Airlines 302
      Sydney (SYD)
      10:15 pm
      Terminal: 1
      Guangzhou (CAN)
      5:00 am
      +1 day
      Arrives on 2 Feb. 2018
      Cabin: Economy (V)
      9h 45m duration
      Seat:
      10A

  The year comes from the `Travel dates` line. This template names the
  airline but never gives its IATA code.

Segments after the first in a leg carry no date of their own; they
depart on the previous segment's arrival date, or the day after if the
departure clock time is earlier than that arrival.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ]
    )
}

LEGACY_LEG_RE = re.compile(
    r"^(?P<day>\d{1,2}) (?P<month>[A-Z][a-z]{2}) (?P<year>\d{4})\n-\n[^\n]+$",
    re.MULTILINE,
)
LEGACY_SEGMENT_RE = re.compile(
    r"^(?P<dep_city>[^\n]+)\n(?P<arr_city>[^\n]+)\n\d+ h \d+ m\n"
    r"(?P<dep>[A-Z]{3})\s+(?P<dep_time>\d{1,2}:\d{2})\s+"
    r"(?P<arr>[A-Z]{3})\s+(?P<arr_time>\d{1,2}:\d{2})\s+"
    r"(?:\(?(?P<offset>[+-]\d) days?\)?\n)?"
    r"(?P<airline>[^\n]+?) (?P<number>\d{1,4})\n"
    r"(?P<cabin>[^\n]+)\n\((?P<booking_class>[A-Z])\)$",
    re.MULTILINE,
)
LEGACY_LOGO_RE = re.compile(
    r"images/airlines/sm(?P<code>[A-Z0-9]{2})\.gif", re.IGNORECASE
)
LEGACY_LOCATORS_RE = re.compile(
    r"^CONFIRMED\n(?P<pairs>.*?)\nExpedia Booking ID$", re.MULTILINE | re.DOTALL
)
LEGACY_TRAVELLERS_RE = re.compile(
    r"^Traveller Information\n(?P<block>.*?)^\*$", re.MULTILINE | re.DOTALL
)
LEGACY_TRAVELLER_RE = re.compile(
    r"^(?:(?:Mr|Mrs|Ms|Miss|Mstr|Dr)\.? )?(?P<name>[^\n]+)\n"
    r"(?:Adult|Child|Infant|Senior|Youth)\b",
    re.MULTILINE,
)
LEGACY_TICKET_RE = re.compile(r"^Ticket # (\d{10,14})$", re.MULTILINE)

_DAY_MONTH = r"(?P<day>\d{1,2}) (?P<month>[A-Z][a-z]{2,3})\.?"
TRAVEL_DATES_RE = re.compile(
    rf"^Travel dates\n{_DAY_MONTH} (?P<year>\d{{4}}) -", re.MULTILINE
)
LEG_RE = re.compile(rf"^[^\n]+\n[A-Z][a-z]{{2}}\.?, {_DAY_MONTH}$", re.MULTILINE)
_CLOCK = r"\d{1,2}:\d{2} [ap]m"
SEGMENT_RE = re.compile(
    r"^(?P<airline>[^\n]+?) (?P<number>\d{1,4})\n"
    r"(?P<dep_city>[^\n(]+?) \((?P<dep>[A-Z]{3})\)\n"
    rf"(?P<dep_time>{_CLOCK})\n"
    r"(?:Terminal: (?P<dep_terminal>[^\n]+)\n)?"
    r"(?P<arr_city>[^\n(]+?) \((?P<arr>[A-Z]{3})\)\n"
    rf"(?P<arr_time>{_CLOCK})\n"
    r"(?:[+-]\d+ days?\n)?"
    r"(?:Arrives on (?P<arr_day>\d{1,2}) (?P<arr_month>[A-Z][a-z]{2,3})\.? "
    r"(?P<arr_year>\d{4})\n)?"
    r"(?:Terminal: (?P<arr_terminal>[^\n]+)\n)?"
    r"Cabin: (?P<cabin>[^\n(]+?)(?: \((?P<booking_class>[A-Z])\))?\n"
    r"(?:[^\n]* duration\n)?"
    r"(?:Seat:\n(?P<seat>\d{1,3}[A-Z])\n)?",
    re.MULTILINE,
)
LOCATOR_RE = re.compile(
    r"^(?P<pnr>[A-Z0-9]{5,8}) \((?P<airline>[^)\n]+)\)$", re.MULTILINE
)
TRAVELLERS_RE = re.compile(
    r"^Traveller\(s\)\n(?P<block>.*?)\nFrequent flyer", re.MULTILINE | re.DOTALL
)
# A loyalty-programme line pair under a traveller's name: the
# programme, then the carrier code and membership number.
LOYALTY_NUMBER_RE = re.compile(r"^[A-Z0-9]{2} \S+$")


def month_number(name: str) -> int:
    return _MONTHS[name[:3].lower()]


def airport(iata: str, city: str, terminal: str | None = None) -> dict:
    out = {"@type": "Airport", "iataCode": iata, "address": city.strip()}
    if terminal:
        out["alternateName"] = f"Terminal {terminal.strip()}"
    return out


def parse_clock(value: str) -> time:
    return datetime.strptime(value.upper(), "%I:%M %p").time()


def next_departure_date(previous_arrival: datetime | None, dep_clock: time) -> date:
    """Departure date of a connecting segment that has no date of its own."""
    if previous_arrival is None:
        raise ValueError("connecting segment without a preceding segment")
    day = previous_arrival.date()
    if dep_clock < previous_arrival.time():
        day += timedelta(days=1)
    return day


def pick_locator(locators: dict[str, str], airline: str) -> str:
    if airline in locators:
        return locators[airline]
    if len(set(locators.values())) == 1:
        return next(iter(locators.values()))
    raise ValueError(f"no booking reference for {airline!r} among {locators!r}")


def legacy_segments(text: str, html: str) -> list[dict]:
    locators_match = LEGACY_LOCATORS_RE.search(text)
    if not locators_match:
        return []
    pairs = locators_match.group("pairs").split("\n")
    if len(pairs) % 2:
        raise ValueError(f"unpaired airline locators: {pairs!r}")
    locators = dict(zip(pairs[::2], pairs[1::2], strict=True))

    passengers: list[str] = []
    tickets: list[str] = []
    if travellers := LEGACY_TRAVELLERS_RE.search(text):
        block = travellers.group("block")
        passengers = [m.group("name") for m in LEGACY_TRAVELLER_RE.finditer(block)]
        tickets = LEGACY_TICKET_RE.findall(block)

    legs = list(LEGACY_LEG_RE.finditer(text))
    segments = list(LEGACY_SEGMENT_RE.finditer(text))
    # One logo per segment, in order; only trust the codes when the
    # counts line up.
    codes: list[str | None] = [
        m.group("code").upper() for m in LEGACY_LOGO_RE.finditer(html)
    ]
    if len(codes) != len(segments):
        codes = [None] * len(segments)

    out = []
    previous_arrival: datetime | None = None
    current_leg = None
    for seg, code in zip(segments, codes, strict=True):
        leg = next((m for m in reversed(legs) if m.start() < seg.start()), None)
        if leg is None:
            raise ValueError(f"segment without a leg date: {seg.group(0)!r}")
        dep_clock = datetime.strptime(seg.group("dep_time"), "%H:%M").time()
        if leg is not current_leg:
            current_leg = leg
            dep_day = date(
                int(leg.group("year")),
                month_number(leg.group("month")),
                int(leg.group("day")),
            )
        else:
            dep_day = next_departure_date(previous_arrival, dep_clock)
        departure = datetime.combine(dep_day, dep_clock)
        arr_day = dep_day + timedelta(days=int(seg.group("offset") or 0))
        arrival = datetime.combine(
            arr_day, datetime.strptime(seg.group("arr_time"), "%H:%M").time()
        )
        previous_arrival = arrival

        airline = {"@type": "Airline", "name": seg.group("airline")}
        if code:
            airline["iataCode"] = code
        reservation = {
            "reservationNumber": pick_locator(locators, seg.group("airline")),
            "reservationFor": {
                "@type": "Flight",
                "flightNumber": seg.group("number"),
                "airline": airline,
                "departureAirport": airport(seg.group("dep"), seg.group("dep_city")),
                "arrivalAirport": airport(seg.group("arr"), seg.group("arr_city")),
                "departureTime": departure.isoformat(),
                "arrivalTime": arrival.isoformat(),
                "pending:cabinClass": seg.group("cabin"),
                "pending:bookingClass": seg.group("booking_class"),
            },
        }
        add_passengers(reservation, passengers)
        if len(tickets) == 1:
            reservation["ticketNumber"] = tickets[0]
        out.append(reservation)
    return out


def modern_segments(text: str) -> list[dict]:
    travel = TRAVEL_DATES_RE.search(text)
    if not travel:
        return []
    start = date(
        int(travel.group("year")),
        month_number(travel.group("month")),
        int(travel.group("day")),
    )
    locators = {m.group("airline"): m.group("pnr") for m in LOCATOR_RE.finditer(text)}
    if not locators:
        raise ValueError("no airline confirmation numbers found")

    passengers: list[str] = []
    if travellers := TRAVELLERS_RE.search(text):
        lines = travellers.group("block").split("\n")
        i = 0
        while i < len(lines):
            passengers.append(lines[i])
            has_loyalty = i + 2 < len(lines) and LOYALTY_NUMBER_RE.match(lines[i + 2])
            i += 3 if has_loyalty else 1

    legs = list(LEG_RE.finditer(text))
    out = []
    previous_arrival: datetime | None = None
    current_leg = None
    for seg in SEGMENT_RE.finditer(text):
        leg = next((m for m in reversed(legs) if m.start() < seg.start()), None)
        if leg is None:
            raise ValueError(f"segment without a leg date: {seg.group(0)!r}")
        dep_clock = parse_clock(seg.group("dep_time"))
        if leg is not current_leg:
            current_leg = leg
            # The leg header has no year: take the first such date on
            # or after the start of travel.
            dep_day = date(
                start.year, month_number(leg.group("month")), int(leg.group("day"))
            )
            if dep_day < start:
                dep_day = dep_day.replace(year=start.year + 1)
        else:
            dep_day = next_departure_date(previous_arrival, dep_clock)
        if seg.group("arr_year"):
            arr_day = date(
                int(seg.group("arr_year")),
                month_number(seg.group("arr_month")),
                int(seg.group("arr_day")),
            )
        else:
            arr_day = dep_day
        departure = datetime.combine(dep_day, dep_clock)
        arrival = datetime.combine(arr_day, parse_clock(seg.group("arr_time")))
        previous_arrival = arrival

        flight = {
            "@type": "Flight",
            "flightNumber": seg.group("number"),
            # TODO: this template carries no IATA code for the airline;
            # map well-known names to codes if the flight-number prefix
            # turns out to matter downstream.
            "airline": {"@type": "Airline", "name": seg.group("airline")},
            "departureAirport": airport(
                seg.group("dep"), seg.group("dep_city"), seg.group("dep_terminal")
            ),
            "arrivalAirport": airport(
                seg.group("arr"), seg.group("arr_city"), seg.group("arr_terminal")
            ),
            "departureTime": departure.isoformat(),
            "arrivalTime": arrival.isoformat(),
            "pending:cabinClass": seg.group("cabin"),
        }
        if seg.group("booking_class"):
            flight["pending:bookingClass"] = seg.group("booking_class")
        reservation: dict = {
            "reservationNumber": pick_locator(locators, seg.group("airline")),
            "reservationFor": flight,
        }
        add_passengers(reservation, passengers)
        if seg.group("seat"):
            reservation["ticketedSeat"] = {
                "@type": "Seat",
                "seatNumber": seg.group("seat"),
            }
        out.append(reservation)
    return out


def add_passengers(reservation: dict, passengers: list[str]) -> None:
    people = [{"@type": "Person", "name": name} for name in passengers]
    if len(people) == 1:
        reservation["underName"] = people[0]
    elif people:
        reservation["underName"] = people


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    text = strip_html(mail.html, block_tags=True)
    text = "\n".join(line.strip() for line in text.split("\n") if line.strip())

    reservations = legacy_segments(text, mail.html) or modern_segments(text)
    for reservation in reservations:
        flight = reservation["reservationFor"]
        full = {
            "@context": {
                "@vocab": "https://schema.org/",
                "pending": "https://pending.schema.org/",
            },
            "@type": "FlightReservation",
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "broker": {"@type": "Organization", "name": "Expedia"},
            **reservation,
        }
        day = flight["departureTime"][:10].replace("-", "")
        slug = (
            f"expedia-{reservation['reservationNumber']}-{day}-{flight['flightNumber']}"
        )
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(full, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
