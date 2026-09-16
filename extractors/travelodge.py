#!/usr/bin/env python3
"""Travelodge booking confirmations.

`webmaster@mail.travelodge.co.uk` sends a booking confirmation with no
schema.org markup. After stripping tags the body is a label/value list:

    Your Confirmation number:<digits>
    ...
    Hotel:
    <hotel name>
    Check in:
    <D Mon YYYY> at <time>
    Check out:
    <D Mon YYYY> at <time>
    Staying in a:
    <room type>

Times are written as `3pm` or `12 noon` rather than a 24-hour clock,
so they're mapped rather than parsed with `strptime`. The same address
also sends a VAT invoice and a cancellation notice under their own
subjects; neither is a confirmation, and the manifest keeps them out.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

CONFIRMATION_RE = re.compile(r"Confirmation number:\s*(\d+)")
HOTEL_RE = re.compile(r"^Hotel:\s*\n\s*(.+?)\s*$", re.MULTILINE)
ROOM_RE = re.compile(r"^Staying in a:\s*\n\s*(.+?)\s*$", re.MULTILINE)
TOTAL_RE = re.compile(
    r"total cost for your booking is:\s*\u00a3\s*([0-9]+(?:\.[0-9]{2})?)"
)
POSTCODE_RE = re.compile(
    r"postcode to find our hotel:\s*([A-Z0-9 ]+?)\s*$", re.MULTILINE
)
CHECKIN_RE = re.compile(
    r"^Check in:\s*\n\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s+at\s+(.+?)\s*$",
    re.MULTILINE,
)
CHECKOUT_RE = re.compile(
    r"^Check out:\s*\n\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s+at\s+(.+?)\s*$",
    re.MULTILINE,
)


def parse_clock(value: str) -> tuple[int, int] | None:
    """Turn Travelodge's `3pm` / `12 noon` / `11:30am` into (hour, minute)."""
    text = value.strip().lower()
    if text in ("12 noon", "noon", "midday"):
        return (12, 0)
    if text in ("midnight", "12 midnight"):
        return (0, 0)
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if match.group(3) == "pm" and hour != 12:
        hour += 12
    elif match.group(3) == "am" and hour == 12:
        hour = 0
    return (hour, minute)


def parse_stamp(day: str, month: str, year: str, clock: str) -> datetime | None:
    parsed = parse_clock(clock)
    if parsed is None:
        return None
    for fmt in ("%b", "%B"):
        try:
            month_num = datetime.strptime(month, fmt).month
        except ValueError:
            continue
        try:
            return datetime(int(year), month_num, int(day), parsed[0], parsed[1])
        except ValueError:
            return None
    return None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html, block_tags=True)

    confirmation = CONFIRMATION_RE.search(text)
    if not confirmation:
        return 0
    reference = confirmation.group(1)

    hotel_match = HOTEL_RE.search(text)
    if not hotel_match:
        return 0
    hotel = hotel_match.group(1)

    checkin_match = CHECKIN_RE.search(text)
    checkout_match = CHECKOUT_RE.search(text)
    if not checkin_match or not checkout_match:
        return 0

    checkin = parse_stamp(*checkin_match.group(1, 2, 3, 4))
    checkout = parse_stamp(*checkout_match.group(1, 2, 3, 4))
    if checkin is None or checkout is None:
        return 0

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationNumber": f"travelodge-{reference}",
        "checkinTime": checkin.strftime("%Y-%m-%dT%H:%M:%S"),
        "checkoutTime": checkout.strftime("%Y-%m-%dT%H:%M:%S"),
        "reservationFor": {
            "@type": "LodgingBusiness",
            "name": f"Travelodge {hotel}",
        },
    }

    postcode_match = POSTCODE_RE.search(text)
    if postcode_match:
        reservation["reservationFor"]["address"] = postcode_match.group(1).strip()

    room_match = ROOM_RE.search(text)
    if room_match:
        reservation["accommodationCategory"] = room_match.group(1)

    total_match = TOTAL_RE.search(text)
    if total_match:
        reservation["totalPrice"] = {
            "@type": "PriceSpecification",
            "price": float(total_match.group(1)),
            "priceCurrency": "GBP",
        }

    Path(f"travelodge-{reference}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
