#!/usr/bin/env python3
"""Eurostar confirmations sent from booking.elgar@eurostar.com, 2017-2019.

After tag-stripping and joining the lines, each journey of the booking
reads:

    Eurostar ES9008 Standard Alpha International To Beta Nord
    Departs : Thur 14 Dec at 07:55 Arrives at 11:17
    Journey Time: 2 hrs 22 mins TEST USER OTHER USER
    Coach 012 , Seat 56 Coach 012 , Seat 55

The line breaks within a journey follow those in the HTML source, so
we don't rely on them.

The journeys have no direction header: the first is the outbound one
and the second the return. The date has no year, so the year is the
one, around the mail's own, on which the date falls on the weekday
given.

We emit one TrainReservation per direction, numbered like the other
Eurostar mails (`eurostar-<reference>-outbound`), with the train
number as the "Your Eurostar Ticket" mails give it (`9008`). The mail
lists the whole booking, so each leg carries
`mailsift:itineraryComplete`.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

REFERENCE_RE = re.compile(r"\bEurostar reference : ([A-Z0-9]{6})\b")
# The fare class separates the train number from the origin.
JOURNEY_RE = re.compile(
    r"\bEurostar ES(?P<train>\d{4}) "
    r"(?:Standard Premier|Business Premier|Standard) "
    r"(?P<origin>.+?) To (?P<destination>.+?) Departs : "
    r"(?P<weekday>[A-Z][a-z]{2,3}) (?P<day>\d{1,2}) (?P<month>[A-Z][a-z]{2}) "
    r"at (?P<dh>\d{2}):(?P<dm>\d{2}) Arrives at (?P<ah>\d{2}):(?P<am>\d{2})\b"
)
TRAIN_RE = re.compile(r"\bEurostar ES\d{4}\b")
SEAT_RE = re.compile(r"\bCoach (\d+) ?, Seat (\w+)")
DIRECTIONS = ("outbound", "return")


def resolve_day(sent: datetime, weekday: str, day: str, month: str) -> datetime:
    """The date within a year of `sent` that falls on `weekday`.

    `weekday` is abbreviated, sometimes to four letters (`Thur`).
    """
    candidates = []
    for year in (sent.year - 1, sent.year, sent.year + 1):
        try:
            candidate = datetime.strptime(f"{day} {month} {year}", "%d %b %Y")
        except ValueError:
            # 29 February outside a leap year.
            continue
        if candidate.strftime("%a") == weekday[:3]:
            candidates.append(candidate)
    if len(candidates) != 1:
        raise ValueError(f"can't place {weekday} {day} {month} around {sent:%Y}")
    return candidates[0]


def parse_leg(text: str, sent: datetime) -> dict:
    """`text` runs from the train number to the next journey."""
    m = JOURNEY_RE.match(text)
    if m is None:
        raise ValueError(f"unrecognised journey {text[:200]!r}")
    date = resolve_day(sent, m["weekday"], m["day"], m["month"])
    departs = date.replace(hour=int(m["dh"]), minute=int(m["dm"]))
    arrives = date.replace(hour=int(m["ah"]), minute=int(m["am"]))
    if arrives < departs:
        arrives += timedelta(days=1)

    leg: dict = {
        "reservationFor": {
            "@type": "TrainTrip",
            "provider": {"@type": "Organization", "name": "Eurostar"},
            "departureStation": {"@type": "TrainStation", "name": m["origin"]},
            "arrivalStation": {"@type": "TrainStation", "name": m["destination"]},
            "departureTime": departs.strftime("%Y-%m-%dT%H:%M:%S"),
            "arrivalTime": arrives.strftime("%Y-%m-%dT%H:%M:%S"),
            "trainNumber": m["train"],
        }
    }
    # Each passenger has a seat; the first is enough for the calendar.
    if seat := SEAT_RE.search(text, m.end()):
        leg["ticketedSeat"] = {
            "@type": "Seat",
            "seatSection": seat[1].lstrip("0"),
            "seatNumber": seat[2],
        }
    return leg


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    if mail.date is None:
        raise ValueError("no Date header to place the journeys' dates in")
    sent = mail.date.replace(tzinfo=None)
    text = " ".join(strip_html(mail.html, block_tags=True).split())

    reference_match = REFERENCE_RE.search(text)
    if reference_match is None:
        raise ValueError("no booking reference")
    reference = reference_match[1]

    starts = [m.start() for m in TRAIN_RE.finditer(text)]
    if not 1 <= len(starts) <= len(DIRECTIONS):
        raise ValueError(f"booking {reference} has {len(starts)} journeys")
    ends = starts[1:] + [len(text)]
    for direction, start, end in zip(DIRECTIONS, starts, ends, strict=False):
        slug = f"eurostar-{reference}-{direction}"
        reservation = {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": slug,
            "mailsift:itineraryComplete": True,
            **parse_leg(text[start:end], sent),
        }
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
