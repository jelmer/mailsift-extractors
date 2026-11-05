#!/usr/bin/env python3
"""Deutsche Bahn booking confirmations.

The mail body is boilerplate in every language bahn.de sends (German,
English, Dutch); the journey is only in the attached Online-Ticket
PDF. Read with pypdf's layout mode, each direction is a table:

    Ihre Reiseverbindung und Reservierung Hinfahrt am 14.03.2041
    Halt                 Datum   Zeit      Gleis   Produkte/Reservierung
    Bremen Hbf           14.03.  ab 21:05  7       CNL 1234, 1 Liegeplatz, Wg. 101,
    Basel Bad Bf         15.03.  an 06:40  2       Pl. 33, 1 Unten, Abteil,
                                                   Nichtraucher
    Basel Bad Bf         15.03.  ab 06:52  3       ICE 271

An `ab` row starts a leg and the next `an` row ends it. The seat
reservation wraps over as many lines as it needs, each but the last
ending in a comma. The header says `Rückfahrt` for a return and
`- Einfache Fahrt` in newer tickets.

We emit one TrainReservation per leg. `reservationNumber` is the order
number, which is also all a cancellation mail gives; the legs of an
order are told apart by their `trainNumber`. Every leg has one (a leg
without a train fails to parse). Older tickets give S-Bahn and
regional trains by line ("S 3"), so an order can list the same one
twice, out and back; those legs get the departure date appended to the
train number ("S 3 (2040-03-23)") to keep them apart. BahnCard
purchases come with a PDF too, but without a journey; those are
skipped.

Cancellation mails ("Confirmation of cancellation (order <code>)",
"Annuleringsbevestiging (Order <code>)") have no PDF and only give the
order number and refund, not the legs; they are handled by
`deutsche-bahn-cancellation`.
"""

from __future__ import annotations

import io
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

ORDER_RE = re.compile(
    r"\((?:Auftrag|Order|bestelling|order):?\s*([A-Z0-9]+)\)", re.IGNORECASE
)
SECTION_RE = re.compile(
    r"Ihre Reiseverbindung und Reservierung\s+(?:-\s+)?"
    r"(Hinfahrt|Rückfahrt|Einfache Fahrt) am (\d{2}\.\d{2}\.\d{4})"
)
ROW_RE = re.compile(
    r"^\s*(?P<station>\S.*?)\s+(?P<day>\d{2})\.(?P<month>\d{2})\.\s+"
    r"(?P<kind>ab|an)\s+(?P<time>\d{2}:\d{2})"
)
# A table cell: words one space apart. Columns are further apart.
CELL_RE = re.compile(r"\S+(?: \S+)*")
# The column after "Gleis" holds the train and the seat booking.
PRODUCTS_COLUMN_RE = re.compile(r"\bGleis\s+(\S)")
# Older tickets print the passenger and order number in a column to the
# right of the table, on the same lines as its rows.
RIGHT_COLUMN_RE = re.compile(r"\s{3,}(?:Herr|Frau|ID-Karte:|Auftragsnummer:)\s.*$")
PRODUCT_RE = re.compile(r"^([A-Z]{1,4}) ?(\d+)(?: \(\d+\))?(?:,\s*|\s{2,}|$)")
PASSENGER_RE = re.compile(r"(?:^|\s{3,})(?:Herr|Frau)\s+(\S.*?)\s*$", re.MULTILINE)
PLACES_RE = re.compile(r"(\d+) (Sitzpl\w*|Liegepl\w*|Schlafwagenpl\w*|Bett\w*)")
COACH_RE = re.compile(r"Wg\. (\w+)")
SEATS_RE = re.compile(r"Pl\. (\d+(?: \d+)*)")
SEATING_TYPES = {
    "Sitz": "Seat",
    "Lieg": "Couchette",
    "Schl": "Sleeper",
    "Bett": "Sleeper",
}


@dataclass
class Leg:
    origin: str
    destination: str
    departs: datetime
    arrives: datetime
    train: str
    reservation: str
    departure_platform: str | None
    arrival_platform: str | None


def stamp(day: str, month: str, time: str, start: datetime) -> datetime:
    """Rows carry no year; a leg can only run into the following one."""
    hour, minute = time.split(":")
    moment = start.replace(
        month=int(month), day=int(day), hour=int(hour), minute=int(minute)
    )
    if moment < start - timedelta(days=1):
        moment = moment.replace(year=moment.year + 1)
    return moment


def split_row(line: str, after: int, products: int) -> tuple[str | None, str]:
    """The platform and the products of a row, by the column each cell
    of `line` from `after` on starts in."""
    platform: str | None = None
    for cell in CELL_RE.finditer(line, after):
        if cell.start() >= products:
            return platform, line[cell.start() :].strip()
        if platform is not None:
            raise ValueError(f"two platforms in {line.strip()!r}")
        platform = cell[0]
    return platform, ""


def parse_section(start: datetime, header: str, lines: list[str]) -> list[Leg]:
    column = PRODUCTS_COLUMN_RE.search(header)
    if column is None:
        raise ValueError(f"no Gleis column in {header.strip()!r}")
    products = column.start(1)
    legs: list[Leg] = []
    pending: dict | None = None
    wrapping = False
    for raw in lines:
        line = RIGHT_COLUMN_RE.sub("", raw)
        row = ROW_RE.match(line)
        if row is None:
            if wrapping and line.strip():
                legs[-1].reservation += " " + line.strip()
                wrapping = line.rstrip().endswith(",")
                continue
            if pending is not None:
                raise ValueError(f"departure from {pending['station']} has no arrival")
            break
        moment = stamp(row["day"], row["month"], row["time"], start)
        platform, rest = split_row(line, row.end(), products)
        if row["kind"] == "ab":
            if pending is not None:
                raise ValueError(f"two departures in a row at {row['station']}")
            pending = {
                "station": row["station"],
                "moment": moment,
                "platform": platform,
                "rest": rest,
            }
            wrapping = False
            continue
        if pending is None:
            raise ValueError(f"arrival at {row['station']} without a departure")
        product = PRODUCT_RE.match(pending["rest"])
        if product is None:
            raise ValueError(f"no train for the leg from {pending['station']}")
        train = f"{product[1]} {product[2]}"
        reservation = pending["rest"][product.end() :].strip()
        if rest:
            reservation = f"{reservation} {rest}".strip()
        legs.append(
            Leg(
                origin=pending["station"],
                destination=row["station"],
                departs=pending["moment"],
                arrives=moment,
                train=train,
                reservation=reservation,
                departure_platform=pending["platform"],
                arrival_platform=platform,
            )
        )
        wrapping = reservation.endswith(",")
        pending = None
    if pending is not None:
        raise ValueError(f"departure from {pending['station']} has no arrival")
    return legs


def parse_ticket(text: str) -> list[Leg]:
    sections = list(SECTION_RE.finditer(text))
    legs: list[Leg] = []
    for m in sections:
        start = datetime.strptime(m[2], "%d.%m.%Y")
        body = text[m.end() :].split("\n")[1:]
        if not body or not body[0].strip().startswith("Halt"):
            raise ValueError(f"no timetable after {m[0]!r}")
        found = parse_section(start, body[0], body[1:])
        if not found:
            raise ValueError(f"no legs under {m[0]!r}")
        legs.extend(found)
    return legs


def ticketed_seat(reservation: str) -> dict | None:
    places = PLACES_RE.search(reservation)
    seats = SEATS_RE.search(reservation)
    if places is None or seats is None:
        return None
    seat: dict = {
        "@type": "Seat",
        "seatNumber": seats[1],
        "seatingType": SEATING_TYPES[places[2][:4]],
    }
    if coach := COACH_RE.search(reservation):
        seat["seatSection"] = coach[1]
    return seat


def train_labels(legs: list[Leg]) -> list[str]:
    """The `trainNumber` of each leg, dated where the order repeats it."""
    counts = Counter(leg.train for leg in legs)
    return [
        f"{leg.train} ({leg.departs:%Y-%m-%d})" if counts[leg.train] > 1 else leg.train
        for leg in legs
    ]


def main() -> int:
    mail = read_message()
    order = ORDER_RE.search(mail.subject or "")
    if order is None:
        raise ValueError(f"no order number in {mail.subject!r}")
    # Newer orders attach a ticket per direction.
    pdfs = [a for a in mail.attachments if a.looks_like_pdf()]
    if not pdfs:
        raise ValueError(f"order {order[1]} has no ticket PDF")
    text = "\n".join(
        page.extract_text(extraction_mode="layout")
        for pdf in pdfs
        for page in PdfReader(io.BytesIO(pdf.bytes)).pages
    )
    legs = parse_ticket(text)
    if not legs:
        if "BAHNCARD" in text.upper() and "Reiseverbindung" not in text:
            return 0
        raise ValueError(f"order {order[1]} lists no journey")
    trains = train_labels(legs)
    if len(set(trains)) != len(trains):
        raise ValueError(f"order {order[1]} lists the same train twice a day: {trains}")
    passenger = PASSENGER_RE.search(text)

    for leg, train in zip(legs, trains):
        trip: dict = {
            "@type": "TrainTrip",
            "provider": {"@type": "Organization", "name": "Deutsche Bahn"},
            "trainNumber": train,
            "departureStation": {"@type": "TrainStation", "name": leg.origin},
            "arrivalStation": {"@type": "TrainStation", "name": leg.destination},
            "departureTime": leg.departs.strftime("%Y-%m-%dT%H:%M:%S"),
            "arrivalTime": leg.arrives.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if leg.departure_platform:
            trip["departurePlatform"] = leg.departure_platform
        if leg.arrival_platform:
            trip["arrivalPlatform"] = leg.arrival_platform
        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": order[1],
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "reservationFor": trip,
        }
        if passenger:
            reservation["underName"] = {"@type": "Person", "name": passenger[1]}
        if seat := ticketed_seat(leg.reservation):
            reservation["reservedTicket"] = {"@type": "Ticket", "ticketedSeat": seat}
        slug = re.sub(r"[^a-z0-9]+", "-", f"{order[1]}-{train}".lower()).strip("-")
        Path(f"deutsche-bahn-{slug}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
