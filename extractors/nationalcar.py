#!/usr/bin/env python3
"""National Car Rental reservation confirmations.

Subject is `National Reservation Confirmation <number> for <location>`,
sent from `reservations@nationalcar.com`. The stripped body is a run of
labelled lines:

    Your confirmation number is: 0000000000.
    Your Vehicle
    Midsize Hyundai Elantra
    or similar
    Trip Details
    Pickup
    Example Intl Airport (EXA)
    August 29, 2026 07:00 PM
    ...
    Return
    Example Intl Airport (EXA)
    September 10, 2026 11:00 PM

Both `Pickup` and `Return` are followed by the branch and then the
date, so a one-way hire keeps both ends. We emit a
`RentalCarReservation`.

Two other layouts carry the same confirmation number, so they
overwrite the same file:

- Bookings made through a partner site come from
  `no-reply@partnerbookingkit.com` ("National Car Rental Confirmation:
  <number>"), with `Pickup Date & Time` / `Thu, Sep 14 2046 3:00 PM`,
  `Pickup Location` / branch, the same for `Return`, and `Vehicle
  Information` / class / model.
- "Modified Reservation: ..." mails list `PICK UP` / branch /
  `Wednesday, September 13, 2046` / `3:00 PM`, the same under
  `RETURN`, and `Vehicle` / class / model.

National doesn't DKIM-sign this mail (only SPF passes), so the
manifest can't require a signature.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

CONFIRMATION_RE = re.compile(r"confirmation number is:?\s*(\d{6,})", re.IGNORECASE)
SUBJECT_RE = re.compile(r"National Reservation Confirmation\s+(\d{6,})", re.IGNORECASE)
# `August 29, 2017 07:00 PM`
WHEN_RE = re.compile(
    r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\s+(\d{1,2}):(\d{2})\s*([AP]M)$",
    re.IGNORECASE,
)

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


def parse_when(value: str) -> datetime | None:
    m = WHEN_RE.match(value.strip())
    if not m:
        return None
    month_name, day, year, hour, minute, meridiem = m.groups()
    month = MONTHS.get(month_name.lower())
    if month is None:
        return None
    hour = int(hour) % 12
    if meridiem.upper() == "PM":
        hour += 12
    try:
        return datetime(int(year), month, int(day), hour, int(minute))
    except ValueError:
        return None


def branch_and_time(lines: list[str], label: str) -> tuple[str | None, datetime | None]:
    """`label` is followed by the branch name, then the date line."""
    for i, line in enumerate(lines):
        if line.strip().lower() != label.lower():
            continue
        branch = None
        for candidate in lines[i + 1 : i + 4]:
            when = parse_when(candidate)
            if when is not None:
                return branch, when
            if branch is None:
                branch = candidate.strip()
    return None, None


def value_after(lines: list[str], label: str) -> str | None:
    try:
        return lines[lines.index(label) + 1]
    except (ValueError, IndexError):
        return None


def partner_end(lines: list[str], end: str) -> tuple[str | None, datetime | None]:
    """`Pickup Date & Time` / `Thu, Sep 14 2046 3:00 PM`, `Pickup Location` / branch."""
    when = value_after(lines, f"{end} Date & Time")
    if when is None:
        return None, None
    try:
        at = datetime.strptime(when, "%a, %b %d %Y %I:%M %p")
    except ValueError:
        raise ValueError(f"unrecognised {end.lower()} time {when!r}") from None
    return value_after(lines, f"{end} Location"), at


def modified_end(lines: list[str], label: str) -> tuple[str | None, datetime | None]:
    """`PICK UP` / branch / `Wednesday, September 13, 2046` / `3:00 PM`."""
    try:
        i = lines.index(label)
        branch, day, time = lines[i + 1 : i + 4]
    except ValueError:
        return None, None
    try:
        at = datetime.strptime(f"{day} {time}", "%A, %B %d, %Y %I:%M %p")
    except ValueError:
        raise ValueError(
            f"unrecognised {label.lower()} time {day!r} {time!r}"
        ) from None
    return branch, at


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).split("\n")
        if line.strip()
    ]

    match = CONFIRMATION_RE.search("\n".join(lines)) or SUBJECT_RE.search(
        mail.subject or ""
    )
    if not match:
        return 0
    confirmation = match.group(1)

    vehicle_label = "Your vehicle"
    pickup_branch, pickup_at = branch_and_time(lines, "Pickup")
    dropoff_branch, dropoff_at = branch_and_time(lines, "Return")
    if pickup_at is None:
        pickup_branch, pickup_at = partner_end(lines, "Pickup")
        dropoff_branch, dropoff_at = partner_end(lines, "Return")
        vehicle_label = "Vehicle Information"
    if pickup_at is None:
        pickup_branch, pickup_at = modified_end(lines, "PICK UP")
        dropoff_branch, dropoff_at = modified_end(lines, "RETURN")
        vehicle_label = "Vehicle"
    if pickup_at is None:
        raise ValueError(f"reservation {confirmation} has no pickup time")

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "RentalCarReservation",
        "reservationNumber": confirmation,
        "provider": {"@type": "Organization", "name": "National Car Rental"},
        "pickupTime": pickup_at.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if dropoff_at is not None:
        reservation["dropoffTime"] = dropoff_at.strftime("%Y-%m-%dT%H:%M:%S")
    if pickup_branch:
        reservation["pickupLocation"] = {"@type": "Place", "name": pickup_branch}
    if dropoff_branch:
        reservation["dropoffLocation"] = {"@type": "Place", "name": dropoff_branch}

    if vehicle_label == "Your vehicle":
        car = next(
            (
                lines[i + 1]
                for i, line in enumerate(lines[:-1])
                if line.lower() == "your vehicle"
            ),
            None,
        )
    else:
        # The class, then the model ("Nissan Versa or similar").
        i = lines.index(vehicle_label) if vehicle_label in lines else -1
        car = (
            " ".join(lines[i + 1 : i + 3]).removesuffix(" or similar")
            if i >= 0
            else None
        )
    if car:
        reservation["reservationFor"] = {"@type": "Car", "name": car}

    Path(f"nationalcar-{confirmation}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
