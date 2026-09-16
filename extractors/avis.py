#!/usr/bin/env python3
"""Avis reservation confirmations.

Subject is `Avis Rent A Car: Reservation Confirmation | <SURNAME> |
Pick-up date: DD/MM/YYYY`. After tag-stripping the body is a run of
labelled lines:

    Pick up:
    Fri Jul 10, 2026 at 12:00 PM
    Drop off:
    Fri Jul 17, 2026 at 12:00 PM
    Your Confirmation Number:
    00000000GB0
    Your Car
    Compact-Toyota Corolla or similar
    ...
    Pick Up Location
    Example Intl Airport,EXA

Avis lists the pickup and drop-off branches separately, so one-way
hires keep both. We emit a `RentalCarReservation`.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

# `Fri Jul 08, 2016 at 12:00 PM`
WHEN_RE = re.compile(
    r"^[A-Za-z]{3}\s+([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})\s+at\s+"
    r"(\d{1,2}):(\d{2})\s*([AP]M)$",
    re.IGNORECASE,
)
CONFIRMATION_RE = re.compile(r"^[A-Z0-9]{8,}$")
AMOUNT_RE = re.compile(r"^[^\d]{0,3}([\d,]+\.\d{2})$")

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
    for i, line in enumerate(lines[:-1]):
        if line.rstrip(":").strip().lower() == label.lower():
            return lines[i + 1].strip()
    return None


def parse_when(value: str | None) -> datetime | None:
    if not value:
        return None
    m = WHEN_RE.match(value.strip())
    if not m:
        return None
    month_name, day, year, hour, minute, meridiem = m.groups()
    month = MONTHS.get(month_name.title())
    if month is None:
        return None
    hour = int(hour) % 12
    if meridiem.upper() == "PM":
        hour += 12
    try:
        return datetime(int(year), month, int(day), hour, int(minute))
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

    confirmation = value_after(lines, "Your Confirmation Number")
    if not confirmation or not CONFIRMATION_RE.match(confirmation):
        return 0

    pickup_at = parse_when(value_after(lines, "Pick up"))
    if pickup_at is None:
        return 0
    dropoff_at = parse_when(value_after(lines, "Drop off"))

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "RentalCarReservation",
        "reservationNumber": confirmation,
        "provider": {"@type": "Organization", "name": "Avis"},
        "pickupTime": pickup_at.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if dropoff_at is not None:
        reservation["dropoffTime"] = dropoff_at.strftime("%Y-%m-%dT%H:%M:%S")

    pickup_branch = value_after(lines, "Pick Up Location")
    if pickup_branch:
        reservation["pickupLocation"] = {"@type": "Place", "name": pickup_branch}
    dropoff_branch = value_after(lines, "Drop Off Location")
    if dropoff_branch:
        reservation["dropoffLocation"] = {"@type": "Place", "name": dropoff_branch}

    car = value_after(lines, "Your Car")
    if car:
        reservation["reservationFor"] = {"@type": "Car", "name": car}

    total = value_after(lines, "Estimated Total")
    if total:
        amount = AMOUNT_RE.match(total)
        if amount:
            reservation["totalPrice"] = {
                "@type": "PriceSpecification",
                "price": float(amount.group(1).replace(",", "")),
            }

    Path(f"avis-{confirmation.lower()}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
