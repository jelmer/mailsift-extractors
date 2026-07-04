#!/usr/bin/env python3
"""Stena Line ferry e-ticket confirmations.

Stena Line e-tickets come from `noreply.integration@stenaline.com`.
The HTML body has a stable layout where the booking reference, the
"FROM - TO" route, the ship name, and the departure/arrival
date+time are all in their own rows.

After stripping tags the relevant block looks like:

    BOOKING REFERENCE:
    90000000
    HARWICH - HOOK OF HOLLAND
    Ship
    Stena Britannica
    Departs
    lör 2025-05-10
    23:00
    Arrives
    sön 2025-05-11
    08:00

Stena uses Swedish day-of-week prefixes (mån/tis/ons/tor/fre/lör/sön)
regardless of language; we ignore them and key off the ISO date.

We emit a `BoatReservation` so the Rust converter renders an
appropriate "Sailing: X -> Y" calendar event. The Rust side recognises
`departureBoatTerminal` / `arrivalBoatTerminal` for the port names.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


BOOKING_RE = re.compile(r"BOOKING REFERENCE:?\s*\n+\s*(\d{6,12})")
ROUTE_RE = re.compile(
    r"^([A-Z][A-Z .'\-]+?)\s+-\s+([A-Z][A-Z .'\-]+?)\s*$",
    re.MULTILINE,
)
SHIP_RE = re.compile(r"^Ship\s*\n+\s*(.+?)\s*$", re.MULTILINE)
DEP_RE = re.compile(
    r"Departs\s*\n+\s*\S+\s+(\d{4}-\d{2}-\d{2})\s*\n+\s*(\d{1,2}:\d{2})"
)
ARR_RE = re.compile(
    r"Arrives\s*\n+\s*\S+\s+(\d{4}-\d{2}-\d{2})\s*\n+\s*(\d{1,2}:\d{2})"
)
TOTAL_RE = re.compile(r"Total Price\s*\n+\s*([0-9]+(?:[.,][0-9]{2})?)\s*([A-Z]{3})")


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True
        elif tag in ("br", "tr", "p", "div", "h1", "h2", "h3", "td", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False
        elif tag in ("tr", "p", "div", "h1", "h2", "h3", "td", "li"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(body: str) -> str:
    p = _Strip()
    p.feed(body)
    text = "".join(p.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_dt(date_str: str, time_str: str) -> datetime | None:
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html)

    booking_match = BOOKING_RE.search(text)
    route_match = ROUTE_RE.search(text)
    dep_match = DEP_RE.search(text)
    arr_match = ARR_RE.search(text)
    if not (booking_match and route_match and dep_match and arr_match):
        return 0

    booking = booking_match.group(1)
    origin = route_match.group(1).strip().title()
    destination = route_match.group(2).strip().title()

    dep_dt = parse_dt(dep_match.group(1), dep_match.group(2))
    arr_dt = parse_dt(arr_match.group(1), arr_match.group(2))
    if dep_dt is None or arr_dt is None:
        return 0

    ship = None
    if (m := SHIP_RE.search(text)) is not None:
        ship = m.group(1).strip()

    total_price = None
    total_currency = None
    if (m := TOTAL_RE.search(text)) is not None:
        total_price = float(m.group(1).replace(",", "."))
        total_currency = m.group(2)

    trip: dict = {
        "@type": "BoatTrip",
        "departureBoatTerminal": {
            "@type": "BoatTerminal",
            "name": origin,
        },
        "arrivalBoatTerminal": {
            "@type": "BoatTerminal",
            "name": destination,
        },
        "departureTime": dep_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "arrivalTime": arr_dt.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if ship:
        trip["vehicleName"] = ship

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "BoatReservation",
        "reservationNumber": f"stena-{booking}",
        "provider": {"@type": "Organization", "name": "Stena Line"},
        "reservationFor": trip,
    }
    if total_price is not None and total_currency:
        reservation["totalPrice"] = {
            "@type": "PriceSpecification",
            "price": total_price,
            "priceCurrency": total_currency,
        }

    Path(f"stena-{booking}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
