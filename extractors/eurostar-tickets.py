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

We emit one TrainReservation per leg, numbered
`eurostar-<reference>-<direction>` like the confirmations the
`eurostar` extractor reads, and told apart by train number, so a
reissue overwrites in place.

A ticket mail lists every leg of the booking, even the ones already
travelled or left alone by an exchange, so each leg carries
`mailsift:itineraryComplete` and mailsift cancels the legs it replaces.
Since 2026 this is the only mail about an exchange that names the new
trains.

Each passenger's ticket for a leg is a barcode image hosted by Eurostar
(`ticket.eurostar.com/barcode/<reference>/<ticket>?s=<signature>`) with
Apple and Google Wallet links beside it. These only exist in the HTML,
so they are matched to legs by the leg headers' order there. The image
URL becomes the ticket's `ticketToken` and the Wallet links become
actions; nothing is fetched.
"""

from __future__ import annotations

import html as htmllib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

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
HTML_LEG_HEADER_RE = re.compile(
    r">\s*(?:Outbound|Return)(?:\s*\(\d+/\d+\))?\s*<", re.IGNORECASE
)
BARCODE_RE = re.compile(
    r'<img\b[^>]*\bsrc="(https://ticket\.eurostar\.com/barcode/[^"]+)"', re.IGNORECASE
)
WALLET_RE = re.compile(
    r'href="([^"]*tickets-api\.eurostar\.com(?:/|%2F)(apple|google)(?:/|%2F)tickets[^"]*)"',
    re.IGNORECASE,
)
# Amazon SES click tracking: the target is percent-encoded after `/L0/`.
TRACKED_RE = re.compile(r"^https://[^/]+\.awstrack\.me/L0/([^/]+)/")
WALLETS = {"apple": "Add to Apple Wallet", "google": "Add to Google Wallet"}

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


def untracked(url: str) -> str:
    """The link a click-tracking redirect points at, or `url` itself."""
    url = htmllib.unescape(url)
    if m := TRACKED_RE.match(url):
        return unquote(m.group(1))
    return url


def html_leg_tickets(html: str) -> list[dict]:
    """Barcode URLs and Wallet links under each leg header, in order."""
    starts = [m.start() for m in HTML_LEG_HEADER_RE.finditer(html)]
    sections = []
    for start, end in zip(starts, starts[1:] + [len(html)], strict=True):
        chunk = html[start:end]
        barcodes = [htmllib.unescape(m.group(1)) for m in BARCODE_RE.finditer(chunk)]
        wallets: list[tuple[str, str]] = []
        for m in WALLET_RE.finditer(chunk):
            link = (WALLETS[m.group(2).lower()], untracked(m.group(1)))
            if link not in wallets:
                wallets.append(link)
        sections.append({"barcodes": barcodes, "wallets": wallets})
    return sections


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

    directions = {
        i: m.group(1).lower()
        for i, line in enumerate(lines)
        if (m := LEG_HEADER_RE.match(line))
    }
    headers = list(directions)
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
            leg["direction"] = directions[headers[index]]
            leg["header_index"] = index
            legs.append(leg)
    if not legs:
        return 0

    sections = html_leg_tickets(mail.html)
    if len(sections) == len(headers):
        for leg in legs:
            leg.update(sections[leg["header_index"]])
    else:
        print(
            f"booking {reference}: {len(sections)} leg headers in the HTML but "
            f"{len(headers)} in its text; not matching tickets to legs",
            file=sys.stderr,
        )

    slugs = set()
    for leg in legs:
        number = f"eurostar-{reference}-{leg['direction']}"
        slug = f"{number}-{leg['train']}" if leg.get("train") else number
        # Legs of one direction are told apart by their train number.
        if slug in slugs:
            raise ValueError(f"booking {reference} has two legs that are {slug}")
        slugs.add(slug)
        reservation: dict = {
            "@context": "https://schema.org",
            "@type": "TrainReservation",
            "reservationNumber": number,
            "mailsift:itineraryComplete": True,
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
        # One ticket per passenger; the seat parsed is the first one's.
        tickets = [
            {"@type": "Ticket", "ticketToken": url} for url in leg.get("barcodes", [])
        ] or [{"@type": "Ticket"}]
        if leg.get("seat"):
            seat: dict = {"@type": "Seat", "seatNumber": leg["seat"]}
            if leg.get("coach"):
                seat["seatSection"] = leg["coach"]
            tickets[0]["ticketedSeat"] = seat
        if len(tickets) > 1:
            reservation["reservedTicket"] = tickets
        elif len(tickets[0]) > 1:
            reservation["reservedTicket"] = tickets[0]
        if leg.get("wallets"):
            reservation["potentialAction"] = [
                {"@type": "ViewAction", "name": name, "url": url}
                for name, url in leg["wallets"]
            ]
        Path(f"{slug}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
