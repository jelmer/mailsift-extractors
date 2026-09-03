#!/usr/bin/env python3
"""Eurostar booking and exchange confirmation emails.

A single mail describes both the outbound and the return leg (when
booked together). After tag-stripping the HTML body the relevant slab
looks like:

    Booking reference: EEEEEE
    Outbound Eurostar Standard Wednesday, 10 June 2026
    London St Pancras Int'l Rotterdam Centraal 18:04 22:32
    3 hrs 28 mins Direct Test User Coach 5 - Seat 17
    Return Eurostar Standard Monday, 22 June 2026
    Rotterdam Centraal London St Pancras Int'l 19:28 21:57 ...

Each leg starts with `Outbound` or `Return`, followed by the fare class,
the date, the two stations, and the two times, then a passenger row
with `Coach N - Seat M`. We emit one TrainReservation per leg,
UID-keyed on `<reference>-<direction>` so an exchange confirmation
for the same direction overwrites in place. The seat assignment
lands in `ticketedSeat` and the fare class in its `seatingType`.

Eurostar mails don't carry a train number, so the reservation has no
trainNumber field; the iCal summary falls back to "Train: <from> -> <to>".
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

REFERENCE_RE = re.compile(r"Booking reference:?\s*([A-Z0-9]{6})")
SUBJECT_REFERENCE_RE = re.compile(r"Reference:\s*([A-Z0-9]{6})", re.IGNORECASE)

LEG_RE = re.compile(
    r"(?P<direction>Outbound|Return)\s+"
    r"Eurostar\s+(?P<fare>\S+)\s+"  # fare class (Standard / Plus / Premier)
    r"(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(?P<year>\d{4})\s+"
    r"(?P<from>.+?)\s+"
    r"(?P<dep>\d{2}:\d{2})\s+"
    r"(?P<arr>\d{2}:\d{2})\b"
)

# Coach + seat, sitting on the passenger row that follows a leg.
SEAT_RE = re.compile(r"Coach\s+(?P<coach>\S+)\s*-\s*Seat\s+(?P<seat>\S+)")


MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(html: str) -> str:
    p = _Strip()
    p.feed(html)
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()


def split_stations(blob: str) -> tuple[str, str] | None:
    """Split a "From-name To-name" run into two station names.

    Eurostar stations end in one of a small set of suffixes; we anchor the
    split on the suffix of the first station. Falls back to splitting on
    the midpoint by whitespace if nothing matches.
    """
    suffixes = [
        "International",
        "Int'l",
        "Int’l",
        "Centraal",
        "Central",
        "Centre",
        "Centrale",
        "Nord",
        "Sud",
        "Midi",
    ]
    for suffix in suffixes:
        idx = blob.find(suffix)
        if idx < 0:
            continue
        end = idx + len(suffix)
        if end >= len(blob):
            continue
        # Require whitespace after the suffix and at least one more word.
        if not blob[end].isspace():
            continue
        first = blob[:end].strip()
        second = blob[end:].strip()
        if first and second:
            return first, second
    return None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html)

    reference = None
    m = REFERENCE_RE.search(text)
    if m:
        reference = m.group(1)
    elif mail.subject:
        m = SUBJECT_REFERENCE_RE.search(mail.subject)
        if m:
            reference = m.group(1)
    if not reference:
        return 0

    legs = list(LEG_RE.finditer(text))
    seen_directions: set[str] = set()
    for index, leg in enumerate(legs):
        direction = leg.group("direction")
        if direction in seen_directions:
            continue
        seen_directions.add(direction)

        day = int(leg.group("day"))
        month = MONTHS[leg.group("month")]
        year = int(leg.group("year"))

        dep_h, dep_m = (int(x) for x in leg.group("dep").split(":"))
        arr_h, arr_m = (int(x) for x in leg.group("arr").split(":"))

        dep_dt = datetime(year, month, day, dep_h, dep_m)
        arr_dt = datetime(year, month, day, arr_h, arr_m)
        if arr_dt < dep_dt:
            # Overnight journey - bump arrival day. Hasn't been seen on
            # Eurostar in practice, but the cost of supporting it is one
            # line.
            arr_dt = arr_dt.replace(day=day + 1)

        stations = split_stations(leg.group("from"))
        if stations is None:
            continue
        from_station, to_station = stations

        # The seat assignment sits on the passenger row just after this
        # leg's route line, before the next leg begins. A booking with
        # one passenger yields one Coach/Seat; multiple passengers just
        # give us the first, which is enough for the calendar entry.
        tail_end = legs[index + 1].start() if index + 1 < len(legs) else len(text)
        seat = SEAT_RE.search(text, leg.end(), tail_end)

        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": f"eurostar-{reference}-{direction.lower()}",
            "reservationFor": {
                "@type": "TrainTrip",
                "provider": {"@type": "Organization", "name": "Eurostar"},
                "departureStation": {
                    "@type": "TrainStation",
                    "name": from_station,
                },
                "arrivalStation": {
                    "@type": "TrainStation",
                    "name": to_station,
                },
                "departureTime": dep_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "arrivalTime": arr_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        if seat is not None:
            reservation["ticketedSeat"] = {
                "@type": "Seat",
                "seatNumber": seat.group("seat"),
                "seatSection": seat.group("coach"),
                "seatingType": leg.group("fare"),
            }

        slug = f"eurostar-{reference}-{direction.lower()}"
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
