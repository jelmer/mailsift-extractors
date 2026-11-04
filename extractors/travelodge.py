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
also sends a VAT invoice, which the manifest keeps out.

"YOUR TRAVELODGE BOOKING IS CANCELLED" mails repeat the same list
(without the postcode and total), so they emit the same reservation
with `reservationStatus: ReservationCancelled`, which replaces the
booked one.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

CONFIRMATION_RE = re.compile(r"Confirmation number:\s*(\d+)", re.IGNORECASE)
HOTEL_RE = re.compile(r"^Hotel:\s*\n\s*(.+?)\s*$", re.MULTILINE)
ROOM_RE = re.compile(r"^Staying in a:\s*\n\s*(.+?)\s*$", re.MULTILINE)
TOTAL_RE = re.compile(
    r"total cost for your booking is:\s*\u00a3\s*([0-9]+(?:\.[0-9]{2})?)"
)
POSTCODE_RE = re.compile(
    r"postcode to find our hotel:\s*([A-Z0-9 ]+?)\s*$", re.MULTILINE
)
CANCELLED_SUBJECT_RE = re.compile(
    r"^Your Travelodge booking is cancell?ed$", re.IGNORECASE
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


def parse_stay(text: str) -> dict | None:
    """The reservation number, hotel, times and room shared by both mails."""
    confirmation = CONFIRMATION_RE.search(text)
    if not confirmation:
        return None
    hotel_match = HOTEL_RE.search(text)
    checkin_match = CHECKIN_RE.search(text)
    checkout_match = CHECKOUT_RE.search(text)
    if not hotel_match or not checkin_match or not checkout_match:
        return None
    checkin = parse_stamp(*checkin_match.group(1, 2, 3, 4))
    checkout = parse_stamp(*checkout_match.group(1, 2, 3, 4))
    if checkin is None or checkout is None:
        return None

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationNumber": f"travelodge-{confirmation.group(1)}",
        "checkinTime": checkin.strftime("%Y-%m-%dT%H:%M:%S"),
        "checkoutTime": checkout.strftime("%Y-%m-%dT%H:%M:%S"),
        "reservationFor": {
            "@type": "LodgingBusiness",
            "name": f"Travelodge {hotel_match.group(1)}",
        },
    }
    room_match = ROOM_RE.search(text)
    if room_match:
        reservation["accommodationCategory"] = room_match.group(1)
    return reservation


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html, block_tags=True)
    reservation = parse_stay(text)

    if CANCELLED_SUBJECT_RE.match((mail.subject or "").strip()):
        if reservation is None:
            raise ValueError("cancellation lacks the booking number, hotel or dates")
        reservation["reservationStatus"] = "ReservationCancelled"
        Path(f"{reservation['reservationNumber']}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
        return 0

    if reservation is None:
        return 0

    postcode_match = POSTCODE_RE.search(text)
    if postcode_match:
        reservation["reservationFor"]["address"] = postcode_match.group(1).strip()

    total_match = TOTAL_RE.search(text)
    if total_match:
        reservation["totalPrice"] = {
            "@type": "PriceSpecification",
            "price": float(total_match.group(1)),
            "priceCurrency": "GBP",
        }

    Path(f"{reservation['reservationNumber']}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
