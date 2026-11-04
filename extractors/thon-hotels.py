#!/usr/bin/env python3
"""Thon Hotels booking confirmations.

Thon's confirmation mails carry no schema.org markup, only a rendered
HTML page. The values sit under Thon's own labels, which this reads
them by:

    Ref. <digits>                 "Ref.: <digits>" since 2026
    1 room, N nights, M adult(s)
    <DDD DD. MMM YYYY>
    Check-in from HH:MM           HH.MM on older and Norwegian ones
    <DDD DD. MMM YYYY>
    Check out before HH:MM
    ...
    Total
    EUR <amount>
    ...
    Address
    <street, city, CC>            on the "Address" line since 2026

The hotel's name comes from the subject, "Booking Confirmation <hotel>".
We emit a single `LodgingReservation`.

"Your reservation at <hotel> has been cancelled" mails ("Stay
cancelled") repeat the Ref. and both dates, unlabelled and without the
clock times, so they emit the same reservation with dates only and
`reservationStatus: ReservationCancelled`, which replaces the booked
one.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

CONFIRMED_SUBJECT_RE = re.compile(r"^Booking Confirmation (Thon .+)$", re.IGNORECASE)
CANCELLED_SUBJECT_RE = re.compile(
    r"^Your reservation at (.+) has been cancel+ed$", re.IGNORECASE
)
REF_RE = re.compile(r"^Ref\.:? ?(\d+)$")
# The older template breaks the line before ", M adults".
COMPOSITION_RE = re.compile(
    r"(?P<rooms>\d+) rooms?, \d+ nights?\n?, (?P<adults>\d+) adults?",
    re.IGNORECASE,
)
CHECKIN_RE = re.compile(r"^Check-in from (\d{1,2})[.:](\d{2})$")
CHECKOUT_RE = re.compile(r"^Check out before (\d{1,2})[.:](\d{2})$")
DATE_RE = re.compile(r"^[A-Z][a-z]{2} (\d{1,2})\. ([A-Z][a-z]{2}) (\d{4})$")
# "EUR 252.00", or "NOK 2 152" with a space between thousands.
PRICE_RE = re.compile(r"^([A-Z]{3}) (\d{1,3}(?: \d{3})*(?:[.,]\d{2})?)$")


def text_lines(html: str) -> list[str]:
    text = strip_html(html, block_tags=True)
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def parse_date(line: str) -> datetime:
    m = DATE_RE.match(line)
    if m is None:
        raise ValueError(f"not a date: {line!r}")
    # Thon writes "30. Jan 2026" in English month names on every locale.
    return datetime.strptime(f"{m[1]} {m[2]} {m[3]}", "%d %b %Y")


def reference(lines: list[str]) -> tuple[int, str]:
    for i, line in enumerate(lines):
        if m := REF_RE.match(line):
            return i, m[1]
    raise ValueError("no Ref.")


def stay_time(lines: list[str], label: re.Pattern[str]) -> datetime:
    """The date on the line before `label`, at the time it gives."""
    for i, line in enumerate(lines[1:], start=1):
        if m := label.match(line):
            return parse_date(lines[i - 1]).replace(hour=int(m[1]), minute=int(m[2]))
    raise ValueError(f"no line matching {label.pattern!r}")


def total_price(lines: list[str]) -> dict | None:
    """The amount under "Total". Some mails leave it out."""
    for i, line in enumerate(lines[:-1]):
        if line != "Total":
            continue
        m = PRICE_RE.match(lines[i + 1])
        if m is None:
            return None
        amount = m[2].replace(" ", "").replace(",", ".")
        return {
            "@type": "PriceSpecification",
            "price": float(amount),
            "priceCurrency": m[1],
        }
    raise ValueError("no Total")


def address(lines: list[str]) -> str:
    for i, line in enumerate(lines[:-1]):
        if line == "Address":
            return lines[i + 1]
        if line.startswith("Address "):
            return line.removeprefix("Address ")
    raise ValueError("no Address")


def cancelled_stay(hotel: str, lines: list[str]) -> dict:
    at, ref = reference(lines)
    # Check-in and check-out are the first two dates after the Ref.
    stay = [line for line in lines[at:] if DATE_RE.match(line)][:2]
    if len(stay) != 2:
        raise ValueError(f"cancellation of {ref} has no stay dates")
    return {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationStatus": "ReservationCancelled",
        "reservationNumber": f"thon-{ref}",
        "checkinTime": parse_date(stay[0]).strftime("%Y-%m-%d"),
        "checkoutTime": parse_date(stay[1]).strftime("%Y-%m-%d"),
        "reservationFor": {"@type": "LodgingBusiness", "name": hotel},
    }


def main() -> int:
    mail = read_message()
    if not mail.html:
        raise ValueError("no HTML body")
    lines = text_lines(mail.html)
    subject = " ".join((mail.subject or "").split())

    if cancelled := CANCELLED_SUBJECT_RE.match(subject):
        cancellation = cancelled_stay(cancelled[1], lines)
        Path(f"{cancellation['reservationNumber']}.reservation.json").write_text(
            json.dumps(cancellation, ensure_ascii=False), encoding="utf-8"
        )
        return 0

    confirmed = CONFIRMED_SUBJECT_RE.match(subject)
    if confirmed is None:
        raise ValueError(f"unexpected subject {subject!r}")
    _, ref = reference(lines)
    checkin = stay_time(lines, CHECKIN_RE)
    checkout = stay_time(lines, CHECKOUT_RE)
    composition = COMPOSITION_RE.search("\n".join(lines))

    # An object @context lets us mix the base vocabulary with the
    # pending track (for numAdults, still on pending.schema.org) and
    # tripmate's own namespace (numRooms - no schema.org term).
    context: str | dict = "https://schema.org"
    if composition:
        context = {
            "@vocab": "https://schema.org/",
            "pending": "https://pending.schema.org/",
            "tripmate": "https://jelmer.github.io/tripmate/ns#",
        }

    reservation: dict = {
        "@context": context,
        "@type": "LodgingReservation",
        "reservationNumber": f"thon-{ref}",
        "checkinTime": checkin.strftime("%Y-%m-%dT%H:%M:%S"),
        "checkoutTime": checkout.strftime("%Y-%m-%dT%H:%M:%S"),
        "reservationFor": {
            "@type": "LodgingBusiness",
            "name": confirmed[1],
            "address": address(lines),
        },
    }
    if composition:
        reservation["pending:numAdults"] = int(composition["adults"])
        reservation["tripmate:numRooms"] = int(composition["rooms"])
    if price := total_price(lines):
        reservation["totalPrice"] = price

    Path(f"thon-{ref}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
