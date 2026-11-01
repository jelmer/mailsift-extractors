#!/usr/bin/env python3
"""Flight bookings sent by Amadeus on behalf of airlines and agents,
pre-DKIM (2012-2018).

Amadeus sends confirmations under its own domain for carriers and
travel agents that use it as their reservation system. Three
templates carry flight segments:

- KLM e-tickets from `emailserver*@pop3.amadeus.net`, subject
  `KLM e-Ticket <day> <month> <from> <to>`, in English or Dutch.
  Segments sit in a two-row table: date, flight, cities, arrival
  date, booking class on the first row; times and IATA codes on the
  second.
- "Check My Trip" itineraries from `itinerary@amadeus.com`, subject
  `SURNAME/GIVEN NAMES DDMMMYYYY FROM TO`, used by agents such as
  Expedia. Airports only carry their IATA code in the
  `checkmytrip.com/triptools/XXX` link next to the name.
- Finnair booking confirmations from `no-reply@amadeus.com`, subject
  `Your confirmation, Booking Ref XXXXXX`. Airports are given by city
  name only.

None of these were DKIM-signed; Amadeus started signing (selector
`FND2019Q1`) later. The manifest only lets unsigned mail through if
it was received before 2019.

TODO: the `eticket@amadeus.com` "Your Electronic Ticket Receipt" mail
carries its segments only in a PDF attachment and is not handled.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import Mail, normalize_unicode, read_message, strip_html

_PENDING_CONTEXT = {
    "@vocab": "https://schema.org/",
    "pending": "https://pending.schema.org/",
}

_ENGLISH_MONTHS = {
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

# Three-letter month codes as they appear in the KLM table. The Dutch
# template uses Dutch abbreviations for the three that differ.
_MONTH_CODES = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "MRT": 3,
    "APR": 4,
    "MAY": 5,
    "MEI": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "OKT": 10,
    "NOV": 11,
    "DEC": 12,
}

# Only names the template itself states; other carriers keep just
# their code.
_AIRLINE_NAMES = {"KL": "KLM Royal Dutch Airlines", "AY": "Finnair"}

_TITLES = frozenset({"MR", "MRS", "MS", "MISS", "MSTR", "DR"})


def _airline(code: str, name: str | None = None) -> dict:
    airline = {"@type": "Airline", "iataCode": code}
    name = name or _AIRLINE_NAMES.get(code)
    if name:
        airline["name"] = name
    return airline


def _airport(
    *, iata: str | None = None, name: str | None = None, city: str | None = None
) -> dict:
    airport: dict = {"@type": "Airport"}
    if name:
        airport["name"] = name
    if iata:
        airport["iataCode"] = iata
    if city:
        airport["address"] = {"@type": "PostalAddress", "addressLocality": city}
    return airport


def _person(name: str) -> dict:
    return {"@type": "Person", "name": name}


def _under_name(names: list[str]) -> dict | list[dict]:
    if len(names) == 1:
        return _person(names[0])
    return [_person(n) for n in names]


def _reservation(
    booking: str,
    flight: dict,
    passengers: list[str],
    tickets: list[str],
) -> dict:
    reservation: dict = {
        "@context": _PENDING_CONTEXT,
        "@type": "FlightReservation",
        "reservationNumber": booking,
        "reservationFor": flight,
    }
    if passengers:
        reservation["underName"] = _under_name(passengers)
    # TODO: with several passengers there's no way to attach each
    # ticket number to its own Person in this shape, so it's dropped.
    if len(tickets) == 1:
        reservation["ticketNumber"] = tickets[0]
    return reservation


def _strip_title(name: str) -> str:
    """Amadeus writes names as `GIVEN NAMES TITLE SURNAME`; the title
    is noise once the name is shown back to a person.
    """
    return " ".join(w for w in name.split() if w not in _TITLES)


def _year_for(month: int, day: int, after: date) -> date:
    """Resolve a year-less date to the first occurrence on or after
    `after`.
    """
    for year in (after.year, after.year + 1, after.year + 4):
        try:
            candidate = date(year, month, day)
        except ValueError:
            # 29 February outside a leap year.
            continue
        if candidate >= after:
            return candidate
    raise ValueError(f"no {day:02d}/{month:02d} on or after {after}")


def _lines(html: str) -> list[str]:
    # Collapse source newlines first so only the markup decides where
    # lines break; these templates wrap text mid-sentence.
    text = strip_html(re.sub(r"\s+", " ", html), block_tags=True)
    return [line.strip() for line in text.split("\n") if line.strip()]


def _value_after(lines: list[str], label: str) -> str | None:
    for i, line in enumerate(lines[:-1]):
        if line == label:
            return lines[i + 1]
    return None


class _TableRows(HTMLParser):
    """Collect the text of every table row as a list of cell strings."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._flush()
            self.rows.append([])
        elif tag in ("td", "th"):
            self._flush()
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th", "tr"):
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def _flush(self) -> None:
        if self._cell is not None and self.rows:
            text = normalize_unicode("".join(self._cell))
            self.rows[-1].append(re.sub(r"\s+", " ", text).strip())
        self._cell = None

    def close(self) -> None:
        super().close()
        self._flush()


_KLM_DAY_RE = re.compile(r"^(\d{2})([A-Z]{3})$")
_KLM_FLIGHT_RE = re.compile(r"^([A-Z0-9]{2}) ?(\d{1,4})$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_IATA_RE = re.compile(r"^[A-Z]{3}$")
_KLM_BOOKING_RE = re.compile(r"\b(?:Booking code|Boekingscode): ([A-Z0-9]{5,8})\b")
_KLM_PASSENGER_HEADERS = frozenset({"Passenger Name", "Naam passagier"})


def _klm_date(code: str, after: date) -> date:
    m = _KLM_DAY_RE.match(code)
    if m is None or m.group(2) not in _MONTH_CODES:
        raise ValueError(f"unrecognised date {code!r}")
    return _year_for(_MONTH_CODES[m.group(2)], int(m.group(1)), after)


def _at(day: date, time: str) -> str:
    m = _TIME_RE.match(time)
    if m is None:
        raise ValueError(f"unrecognised time {time!r}")
    dt = datetime(day.year, day.month, day.day, int(m.group(1)), int(m.group(2)))
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _klm_eticket(mail: Mail, sent: date) -> Iterator[tuple[str, dict]]:
    m = _KLM_BOOKING_RE.search(strip_html(mail.html or ""))
    if m is None:
        return
    booking = m.group(1)

    parser = _TableRows()
    parser.feed(mail.html or "")
    parser.close()
    rows = parser.rows

    passengers: list[str] = []
    tickets: list[str] = []
    for i, row in enumerate(rows):
        if row and row[0] in _KLM_PASSENGER_HEADERS:
            for prow in rows[i + 1 :]:
                if len(prow) < 2 or not re.fullmatch(r"\d{3} ?\d{10}", prow[1]):
                    break
                passengers.append(_strip_title(prow[0]))
                tickets.append(prow[1].replace(" ", ""))
            break

    # The send date is UTC and the flight dates are local, so allow a
    # day of slack before rolling a date over to next year.
    previous = sent - timedelta(days=1)
    for row, times in pairwise(rows):
        if len(row) < 6 or len(times) < 5:
            continue
        if not (_KLM_DAY_RE.match(row[0]) and _KLM_FLIGHT_RE.match(row[1])):
            continue
        if not (_TIME_RE.match(times[0]) and _IATA_RE.match(times[2])):
            continue
        fm = _KLM_FLIGHT_RE.match(row[1])
        assert fm is not None
        carrier, number = fm.group(1), fm.group(2).lstrip("0") or "0"
        dep_day = _klm_date(row[0], previous)
        arr_day = _klm_date(row[4], dep_day)
        previous = dep_day
        flight = {
            "@type": "Flight",
            "flightNumber": number,
            "airline": _airline(carrier),
            "departureAirport": _airport(iata=times[2], city=row[2].title()),
            "arrivalAirport": _airport(iata=times[3], city=row[3].title()),
            "departureTime": _at(dep_day, times[0]),
            "arrivalTime": _at(arr_day, times[4]),
            "pending:bookingClass": row[5],
        }
        yield (
            f"amadeus-{booking}-{carrier}{number}",
            _reservation(booking, flight, passengers, tickets),
        )


_WEEKDAY_DATE_RE = re.compile(
    r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) "
    r"(\d{1,2}) ([A-Za-z]+) (\d{4})$"
)
_ITIN_FLIGHT_RE = re.compile(r"^(.+) ([A-Z0-9]{2}) (\d{1,4})$")
_ITIN_TIME_RE = re.compile(r"^(\d{1,2}) ([A-Za-z]+) (\d{1,2}):(\d{2}) (AM|PM)$")
_ITIN_AIRPORT_RE = re.compile(r"^(.+?), \((.+)\) \[([A-Z]{3})\]$")
_ITIN_CLASS_RE = re.compile(r"^(.+?) \(([A-Z])\)$")
_ITIN_TICKET_RE = re.compile(r"^E-ticket (\d{3})-(\d{10}) for (.+)$")
_TRIPTOOLS_RE = re.compile(
    r'<a\b[^>]*href="https?://www\.checkmytrip\.com/triptools/([A-Z]{3})"[^>]*>'
    r"\s*\(\+\)\s*</a>",
    re.IGNORECASE,
)


def _itin_datetime(line: str, after: date) -> datetime:
    m = _ITIN_TIME_RE.match(line)
    if m is None or m.group(2).lower() not in _ENGLISH_MONTHS:
        raise ValueError(f"unrecognised date/time {line!r}")
    day = _year_for(_ENGLISH_MONTHS[m.group(2).lower()], int(m.group(1)), after)
    hour = int(m.group(3)) % 12 + (12 if m.group(5) == "PM" else 0)
    return datetime(day.year, day.month, day.day, hour, int(m.group(4)))


def _itin_airport(line: str) -> dict:
    m = _ITIN_AIRPORT_RE.match(line)
    if m is None:
        raise ValueError(f"unrecognised airport {line!r}")
    return _airport(iata=m.group(3), name=m.group(2), city=m.group(1))


def _itinerary(mail: Mail, sent: date) -> Iterator[tuple[str, dict]]:
    # Bring the IATA code out of the link so it survives flattening.
    html = _TRIPTOOLS_RE.sub(r"[\1]", mail.html or "")
    lines = _lines(html)
    booking = _value_after(lines, "Booking ref:")
    if booking is None:
        return
    # TODO: only seen with one traveller; check how further travellers
    # are listed before reading more than the first.
    traveler = _value_after(lines, "Traveler")
    passengers = [traveler] if traveler else []
    tickets = [
        m.group(1) + m.group(2)
        for m in map(_ITIN_TICKET_RE.match, lines)
        if m is not None
    ]

    day: date | None = None
    for i, line in enumerate(lines):
        if m := _WEEKDAY_DATE_RE.match(line):
            month = _ENGLISH_MONTHS.get(m.group(2).lower())
            if month is None:
                raise ValueError(f"unrecognised date {line!r}")
            day = date(int(m.group(3)), month, int(m.group(1)))
            continue
        fm = _ITIN_FLIGHT_RE.match(line)
        if fm is None or lines[i + 1 : i + 2] != ["Departure"]:
            continue
        if day is None:
            raise ValueError(f"flight {line!r} before any date heading")
        dep = _itin_datetime(lines[i + 2], day)
        dep_airport = _itin_airport(lines[i + 3])
        j = lines.index("Arrival", i + 4)
        arr = _itin_datetime(lines[j + 1], dep.date())
        arr_airport = _itin_airport(lines[j + 2])

        carrier, number = fm.group(2), fm.group(3)
        flight: dict = {
            "@type": "Flight",
            "flightNumber": number,
            "airline": _airline(carrier, fm.group(1)),
            "departureAirport": dep_airport,
            "arrivalAirport": arr_airport,
            "departureTime": dep.strftime("%Y-%m-%dT%H:%M:%S"),
            "arrivalTime": arr.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        # The details list runs until the next flight or date heading.
        for k in range(j + 3, len(lines) - 1):
            if _WEEKDAY_DATE_RE.match(lines[k]) or lines[k + 1] == "Departure":
                break
            if lines[k] == "Class" and (cm := _ITIN_CLASS_RE.match(lines[k + 1])):
                flight["pending:cabinClass"] = cm.group(1)
                flight["pending:bookingClass"] = cm.group(2)
                break
        yield (
            f"amadeus-{booking}-{carrier}{number}",
            _reservation(booking, flight, passengers, tickets),
        )


_FINNAIR_ROUTE_RE = re.compile(r"^(.+?) - (.+)$")
_FINNAIR_FLIGHT_RE = re.compile(
    r"^([A-Z0-9]{2})(\d{1,4}) ([A-Z]) (\d{1,2}:\d{2}) - (\d{1,2}:\d{2})$"
)
_FINNAIR_CABIN_RE = re.compile(r"^(.+) cabin$")
_TERMINAL_RE = re.compile(r"\s*\(Terminal [^)]*\)$")


def _finnair_confirmation(mail: Mail, sent: date) -> Iterator[tuple[str, dict]]:
    lines = _lines(mail.html or "")
    booking = _value_after(lines, "BOOKING REFERENCE:")
    if booking is None:
        return
    passengers = [
        lines[i + 1]
        for i, line in enumerate(lines[:-1])
        if re.fullmatch(r"Passenger \d+:", line)
    ]

    for i in range(len(lines) - 2):
        route = _FINNAIR_ROUTE_RE.match(lines[i])
        day_m = _WEEKDAY_DATE_RE.match(lines[i + 1])
        fm = _FINNAIR_FLIGHT_RE.match(lines[i + 2])
        if route is None or day_m is None or fm is None:
            continue
        month = _ENGLISH_MONTHS.get(day_m.group(2).lower())
        if month is None:
            raise ValueError(f"unrecognised date {lines[i + 1]!r}")
        dep_day = date(int(day_m.group(3)), month, int(day_m.group(1)))
        # Only the departure date is given. A flight that lands at an
        # earlier clock time than it left has crossed midnight.
        departs, arrives = fm.group(4).zfill(5), fm.group(5).zfill(5)
        arr_day = dep_day + timedelta(days=1 if arrives < departs else 0)
        carrier, number = fm.group(1), fm.group(2)
        flight: dict = {
            "@type": "Flight",
            "flightNumber": number,
            "airline": _airline(carrier),
            "departureAirport": _airport(city=_TERMINAL_RE.sub("", route.group(1))),
            "arrivalAirport": _airport(city=_TERMINAL_RE.sub("", route.group(2))),
            "departureTime": _at(dep_day, departs),
            "arrivalTime": _at(arr_day, arrives),
            "pending:bookingClass": fm.group(3),
        }
        if cm := _FINNAIR_CABIN_RE.match(lines[i + 3] if i + 3 < len(lines) else ""):
            flight["pending:cabinClass"] = cm.group(1)
        reservation = _reservation(booking, flight, passengers, [])
        # Seats are listed as `AY2918 12A` per flight. With several
        # passengers the list doesn't say whose seat is whose.
        # TODO: attach seats when there is more than one passenger.
        seat_re = re.compile(rf"^{carrier}{number} (\d{{1,3}}[A-K])$")
        seats = [m.group(1) for m in map(seat_re.match, lines) if m is not None]
        if len(passengers) == 1 and len(seats) == 1:
            reservation["ticketedSeat"] = {"@type": "Seat", "seatNumber": seats[0]}
        yield f"amadeus-{booking}-{carrier}{number}", reservation


_Template = Callable[[Mail, date], Iterator[tuple[str, dict]]]


def _template(mail: Mail) -> _Template | None:
    sender = (mail.from_address or "").lower()
    subject = mail.subject or ""
    if sender.endswith("@pop3.amadeus.net") and subject.startswith("KLM e-Ticket"):
        return _klm_eticket
    if sender == "itinerary@amadeus.com":
        return _itinerary
    if sender == "no-reply@amadeus.com" and subject.startswith(
        "Your confirmation, Booking Ref "
    ):
        return _finnair_confirmation
    return None


def extract(mail: Mail) -> int:
    if not mail.html:
        return 0
    if mail.date is None:
        return 0
    template = _template(mail)
    if template is None:
        return 0
    for slug, reservation in template(mail, mail.date.date()):
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


def main() -> int:
    return extract(read_message())


if __name__ == "__main__":
    sys.exit(main())
