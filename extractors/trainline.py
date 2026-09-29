#!/usr/bin/env python3
"""Trainline booking confirmations.

`auto-confirm@info.thetrainline.com` sends a booking confirmation for
each journey, followed by a separate eticket mail. Only the
confirmation carries the itinerary; after stripping tags its body has
a stable layout:

    Your trip to <destination> departing <weekday>, <D Month YYYY> is confirmed
    ...
    Outbound <weekday>, <D Month>
    <duration>, <n> changes
    HH:MM <origin>
    <operator>
    HH:MM <destination>

A return booking repeats that block under an `Inbound` heading, so we
emit one `TrainReservation` per leg. The year appears only in the
headline; the per-leg headings carry day and month alone.

The mails also attach a `trip.ics`, which `ics-passthrough` turns into
a calendar event. That covers the diary but not the reservation
archive, which is what this extractor is for.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

HEADLINE_RE = re.compile(
    r"Your trip to .+? departing \w+,?\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
)
TRANSACTION_RE = re.compile(r"Transaction ID:\s*\n\s*(\d+)")
TOTAL_RE = re.compile(r"Total amount:\s*\n\s*£\s*([0-9]+(?:\.[0-9]{2})?)")
# Each leg opens with `Outbound`/`Inbound` and a day-and-month heading,
# then a `HH:MM <station>` / operator / `HH:MM <station>` triple.
LEG_RE = re.compile(
    r"^(Outbound|Inbound)\s+\w+,?\s+(\d{1,2})\s+([A-Za-z]+)\s*$",
    re.MULTILINE,
)
STOP_RE = re.compile(r"^(\d{1,2}:\d{2})\s+(.+?)\s*$", re.MULTILINE)


def parse_month(name: str) -> int | None:
    for fmt in ("%B", "%b"):
        try:
            return datetime.strptime(name, fmt).month
        except ValueError:
            continue
    return None


def parse_leg(
    text: str, start: int, end: int, day: str, month: str, year: int
) -> dict | None:
    """Pull the departure and arrival out of one leg's slice."""
    window = text[start:end]
    stops = STOP_RE.findall(window)
    if len(stops) < 2:
        return None

    month_num = parse_month(month)
    if month_num is None:
        return None

    (dep_time, origin), (arr_time, destination) = stops[0], stops[1]
    dep_hh, dep_mm = (int(x) for x in dep_time.split(":"))
    arr_hh, arr_mm = (int(x) for x in arr_time.split(":"))
    try:
        depart = datetime(year, month_num, int(day), dep_hh, dep_mm)
    except ValueError:
        return None
    arrive = depart.replace(hour=arr_hh, minute=arr_mm)
    # A leg that lands earlier than it departs ran past midnight; the
    # heading only ever names the departure day.
    if arrive < depart:
        arrive += timedelta(days=1)

    leg = {
        "origin": origin.strip(),
        "destination": destination.strip(),
        "departs": depart,
        "arrives": arrive,
    }
    # The operator sits on its own line between the two stops.
    between = window.split(dep_time, 1)[-1].split(arr_time, 1)[0]
    lines = [line.strip() for line in between.split("\n") if line.strip()]
    if len(lines) > 1:
        leg["operator"] = lines[-1]
    return leg


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html, block_tags=True)

    headline = HEADLINE_RE.search(text)
    if not headline:
        return 0
    year = int(headline.group(3))

    transaction = TRANSACTION_RE.search(text)
    if not transaction:
        return 0
    reference = transaction.group(1)

    total = None
    total_match = TOTAL_RE.search(text)
    if total_match:
        total = float(total_match.group(1))

    headings = list(LEG_RE.finditer(text))
    if not headings:
        return 0

    legs = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        leg = parse_leg(
            text, heading.end(), end, heading.group(2), heading.group(3), year
        )
        if leg is not None:
            leg["direction"] = heading.group(1).lower()
            legs.append(leg)
    if not legs:
        return 0

    # Direction (outbound/inbound) goes into `reservationNumber` so both
    # legs of a return booking survive as separate calendar events; the
    # bare booking number would collide because downstream sinks key off
    # the reservation number. Delays keep the direction intact, so a
    # rescheduled leg still updates the same event.
    multi_leg = len(legs) > 1
    for index, leg in enumerate(legs):
        direction = leg["direction"]
        number = f"{reference}-{direction}" if multi_leg else reference
        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": number,
            "reservationFor": {
                "@type": "TrainTrip",
                "departureStation": {
                    "@type": "TrainStation",
                    "name": leg["origin"],
                },
                "arrivalStation": {
                    "@type": "TrainStation",
                    "name": leg["destination"],
                },
                "departureTime": leg["departs"].strftime("%Y-%m-%dT%H:%M:%S"),
                "arrivalTime": leg["arrives"].strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        if "operator" in leg:
            reservation["reservationFor"]["provider"] = {
                "@type": "Organization",
                "name": leg["operator"],
            }
        # Price covers the whole booking, so only the first leg carries
        # it; repeating it per leg would double-count a return.
        if total is not None and index == 0:
            reservation["totalPrice"] = {
                "@type": "PriceSpecification",
                "price": total,
                "priceCurrency": "GBP",
            }

        suffix = f"-{direction}" if multi_leg else ""
        Path(f"trainline-{reference}{suffix}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
