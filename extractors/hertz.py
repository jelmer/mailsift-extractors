#!/usr/bin/env python3
"""Hertz reservation confirmations.

Sent as `Your Hertz Reservation <number>` from `noreply@hertz.com` or
`noreply@emails.hertz.com`. After tag-stripping, the itinerary is a
run of labelled lines:

    Your reservation confirmation number is: H0000000000
    Your Itinerary:
    Pickup and Return Location.
    Example City - Airport
    Address
    1 Example Drive
    ...
    Pick Up time
    Fri, 13 Mar, 2026 at 18:00
    Return time
    Sun, 22 Mar, 2026 at 18:00
    ...
    Your Vehicle:
    Economy
    Group A

Hertz names one location when pickup and return are the same branch
(`Pickup and Return Location.`), so the dropoff is left unset and
mailsift renders a single-location hire.

We emit a `RentalCarReservation`. Hertz mail is relayed, so the DKIM
signature is not always hertz.com and the manifest can't require one.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

CONFIRMATION_RE = re.compile(
    r"reservation confirmation number is:?\s*([A-Z0-9]{6,})", re.IGNORECASE
)
SUBJECT_RE = re.compile(r"Your Hertz Reservation\s+([A-Z0-9]{6,})", re.IGNORECASE)
# `Fri, 10 Mar, 2017 at 18:00`
WHEN_RE = re.compile(
    r"^[A-Za-z]{3},\s*(\d{1,2})\s+([A-Za-z]{3}),?\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2})$"
)
TOTAL_RE = re.compile(r"^([\d,]+\.\d{2})\s+([A-Z]{3})$")

MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ],
        start=1,
    )
}


def value_after(lines: list[str], label: str) -> str | None:
    """The line following the first line equal to `label`."""
    for i, line in enumerate(lines[:-1]):
        if line.rstrip(":.").strip().lower() == label.lower():
            return lines[i + 1].strip()
    return None


def parse_when(value: str | None) -> datetime | None:
    if not value:
        return None
    m = WHEN_RE.match(value.strip())
    if not m:
        return None
    day, month_name, year, hour, minute = m.groups()
    month = MONTHS.get(month_name.title())
    if month is None:
        return None
    try:
        return datetime(int(year), month, int(day), int(hour), int(minute))
    except ValueError:
        return None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).split("\n")
        if line.strip()
    ]
    joined = "\n".join(lines)

    match = CONFIRMATION_RE.search(joined) or SUBJECT_RE.search(mail.subject or "")
    if not match:
        return 0
    confirmation = match.group(1)

    pickup_at = parse_when(value_after(lines, "Pick Up time"))
    if pickup_at is None:
        return 0
    dropoff_at = parse_when(value_after(lines, "Return time"))

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "RentalCarReservation",
        "reservationNumber": confirmation,
        "provider": {"@type": "Organization", "name": "Hertz"},
        "pickupTime": pickup_at.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if dropoff_at is not None:
        reservation["dropoffTime"] = dropoff_at.strftime("%Y-%m-%dT%H:%M:%S")

    branch = value_after(lines, "Pickup and Return Location")
    if branch:
        pickup: dict = {"@type": "Place", "name": branch}
        address = value_after(lines, "Address")
        if address:
            pickup["address"] = address
        reservation["pickupLocation"] = pickup

    # The vehicle class sits under `Your Vehicle:`; the line after it
    # is the class ("Economy"), which is what the mail promises.
    vehicle = value_after(lines, "Your Vehicle")
    if vehicle:
        reservation["reservationFor"] = {"@type": "Car", "name": vehicle}

    for line in lines:
        total = TOTAL_RE.match(line)
        if total:
            reservation["totalPrice"] = {
                "@type": "PriceSpecification",
                "price": float(total.group(1).replace(",", "")),
                "priceCurrency": total.group(2),
            }
            break

    Path(f"hertz-{confirmation.lower()}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
