#!/usr/bin/env python3
"""Eurostar ticket-delivery mails ("Your Eurostar tickets to ...").

Distinct from the `eurostar` extractor, which handles the `Booking
confirmation | ...` mails. These are sent when the tickets themselves
are issued and carry more detail than the confirmation: per-leg coach,
seat, train number and ticket number.

After tag-stripping, each leg is a run of labelled lines:

    Outbound
    Tuesday 19 November 2024
    Alpha International
    Beta Central
    06:04
    (local time)
    10:32
    (local time)
    ...
    Coach
    4
    Seat
    12
    TRAIN
    1001

A leg header is `Outbound` or `Return`, and journeys with a connection
number them (`Return (1/2)`). The date line is either
`Tuesday 19 November 2024` or the short `Mon, 30 October` - the latter
has no year, so it's grounded on the mail's own date. The `(local
time)` annotations are optional.

We emit one TrainReservation per leg, UID-keyed on
`<reference>-<index>` so a reissue overwrites in place.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

# `strip_html` collapses the label and its value onto one line, but
# some layouts still split them; accept either.
REFERENCE_RE = re.compile(r"Booking reference:?\s*([A-Z0-9]{6})?\s*$", re.IGNORECASE)
LEG_HEADER_RE = re.compile(r"^(Outbound|Return)(?:\s*\(\d+/\d+\))?$", re.IGNORECASE)
# `Tuesday 19 November 2024` or `Mon, 30 October` (no year).
LONG_DATE_RE = re.compile(r"^[A-Za-z]+,?\s+(\d{1,2})\s+([A-Za-z]+)(?:\s+(\d{4}))?$")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
REFERENCE_VALUE_RE = re.compile(r"^[A-Z0-9]{6}$")

MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        start=1,
    )
}


def resolve_year(ref: datetime, day: int, month: int) -> int:
    """Pick the year for a date line that omits one.

    The short form (`Mon, 30 October`) has no year. Tickets are always
    issued before the journey, so choose the first year that puts the
    date on or after the mail - a January trip booked in December
    belongs to the following year.
    """
    for offset in (0, 1):
        try:
            candidate = datetime(ref.year + offset, month, day)
        except ValueError:
            continue
        if candidate.date() >= ref.date():
            return candidate.year
    return ref.year


def labelled_value(lines: list[str], start: int, label: str, limit: int) -> str | None:
    """Value on the line after `label`, searched within `limit` lines."""
    for i in range(start, min(start + limit, len(lines) - 1)):
        if lines[i].strip().lower() == label.lower():
            return lines[i + 1].strip()
    return None


def parse_leg(lines: list[str], start: int, end: int, ref: datetime) -> dict | None:
    """Parse one leg from the slice between two leg headers."""
    window = lines[start:end]
    date_index = None
    date_match = None
    for i, line in enumerate(window):
        if m := LONG_DATE_RE.match(line):
            date_index = i
            date_match = m
            break
    if date_match is None or date_index is None or date_index + 4 >= len(window):
        return None

    day, month_name, year = date_match.groups()
    month = MONTHS.get(month_name.lower())
    if month is None:
        return None

    origin = window[date_index + 1]
    destination = window[date_index + 2]

    times = [
        m
        for line in window[date_index + 3 : date_index + 8]
        if (m := TIME_RE.match(line))
    ]
    if not times:
        return None

    resolved = int(year) if year else resolve_year(ref, int(day), month)
    try:
        depart = datetime(
            resolved,
            month,
            int(day),
            int(times[0].group(1)),
            int(times[0].group(2)),
        )
    except ValueError:
        return None

    leg = {
        "origin": origin,
        "destination": destination,
        "departs": depart,
        "coach": labelled_value(window, date_index, "Coach", len(window)),
        "seat": labelled_value(window, date_index, "Seat", len(window)),
        "train": labelled_value(window, date_index, "TRAIN", len(window)),
    }
    if len(times) > 1:
        try:
            arrive = datetime(
                depart.year,
                depart.month,
                depart.day,
                int(times[1].group(1)),
                int(times[1].group(2)),
            )
            # An arrival earlier than departure means the leg ran past
            # midnight; the date line only ever names the departure day.
            if arrive < depart:
                arrive = arrive.replace(day=arrive.day + 1)
            leg["arrives"] = arrive
        except ValueError:
            pass
    return leg


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).split("\n")
        if line.strip()
    ]

    reference = None
    for i, line in enumerate(lines):
        match = REFERENCE_RE.match(line)
        if not match:
            continue
        if match.group(1):
            reference = match.group(1)
        elif i + 1 < len(lines) and REFERENCE_VALUE_RE.match(lines[i + 1]):
            reference = lines[i + 1]
        if reference:
            break
    if reference is None:
        return 0

    headers = [i for i, line in enumerate(lines) if LEG_HEADER_RE.match(line)]
    if not headers:
        return 0

    reference_date = mail.date or datetime.now(UTC)
    if reference_date.tzinfo is not None:
        reference_date = reference_date.replace(tzinfo=None)
    bounds = headers + [len(lines)]
    legs = []
    for index in range(len(headers)):
        leg = parse_leg(lines, bounds[index], bounds[index + 1], reference_date)
        if leg is not None:
            legs.append(leg)
    if not legs:
        return 0

    for index, leg in enumerate(legs, start=1):
        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": f"{reference}-{index}",
            "reservationFor": {
                "@type": "TrainTrip",
                "provider": {"@type": "Organization", "name": "Eurostar"},
                "departureStation": {"@type": "TrainStation", "name": leg["origin"]},
                "arrivalStation": {
                    "@type": "TrainStation",
                    "name": leg["destination"],
                },
                "departureTime": leg["departs"].strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        if leg.get("arrives"):
            reservation["reservationFor"]["arrivalTime"] = leg["arrives"].strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
        if leg.get("train"):
            reservation["reservationFor"]["trainNumber"] = leg["train"]
        if leg.get("seat"):
            seat: dict = {"@type": "Seat", "seatNumber": leg["seat"]}
            if leg.get("coach"):
                seat["seatSection"] = leg["coach"]
            reservation["reservedTicket"] = {
                "@type": "Ticket",
                "ticketedSeat": seat,
            }
        Path(f"eurostar-{reference.lower()}-{index}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
