#!/usr/bin/env python3
"""Hostelworld booking confirmations.

Once the tags are stripped, the 2010-2012 template reads:

    Your booking is confirmed. Your reference number is 15093-00000000
    booking information
    <hostel>
    <street>
    <town>
    <country>
    p. <phone>
    ...
    Date
    Room Details
    Per Bed
    Pax
    Total
    Sun 26th Dec 2038
    <room>
    <price per bed>
    <beds>
    <price>
    ...
    Total: <total>

with one row per night. Nights need not be consecutive, so each run
of consecutive nights becomes its own stay. Some mails give the night
as just "Sat 21st"; that is the first such date from the day the mail
was sent.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

REFERENCE_RE = re.compile(r"Your reference number is (\d+-\d+)$")
NIGHT_RE = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\d{1,2})(?:st|nd|rd|th)(?: ([A-Z][a-z]{2}) (\d{4}))?$"
)
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CONTACT_RE = re.compile(r"^(?:p|f|e|email)[.:] ")


def night(m: re.Match, sent: datetime | None) -> date:
    if m.group(3):
        return datetime.strptime(
            f"{m.group(2)} {m.group(3)} {m.group(4)}", "%d %b %Y"
        ).date()
    if sent is None:
        raise ValueError(f"no month or year for {m.group(0)!r} and no Date header")
    day = sent.date() - timedelta(days=1)
    for _ in range(366):
        if day.day == int(m.group(2)) and WEEKDAYS[day.weekday()] == m.group(1):
            return day
        day += timedelta(days=1)
    raise ValueError(f"no {m.group(0)!r} within a year of {sent:%Y-%m-%d}")


def runs(nights: list[date]) -> list[tuple[date, date]]:
    """Group sorted nights into (first night, check-out day) stays."""
    stays: list[tuple[date, date]] = []
    for n in nights:
        if stays and stays[-1][1] == n:
            stays[-1] = (stays[-1][0], n + timedelta(days=1))
        else:
            stays.append((n, n + timedelta(days=1)))
    return stays


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]
    reference = next(
        (m.group(1) for line in lines if (m := REFERENCE_RE.search(line))), None
    )
    if reference is None:
        return 0

    info = lines.index("booking information")
    header = lines.index("Date", info)
    block = lines[info + 1 : header]
    contact = next(
        (i for i, line in enumerate(block) if CONTACT_RE.match(line)), len(block)
    )
    if contact < 4:
        raise ValueError(f"booking {reference}: no address before the contact lines")
    name, *street, town, country = block[:contact]
    hostel: dict = {
        "@type": "Hostel",
        "name": name,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": ", ".join(street),
            "addressLocality": town,
            "addressCountry": country,
        },
    }
    phone = next((line[3:] for line in block if line.startswith("p. ")), None)
    if phone:
        hostel["telephone"] = phone

    nights = sorted(
        {night(m, mail.date) for line in lines[header:] if (m := NIGHT_RE.match(line))}
    )
    if not nights:
        raise ValueError(f"booking {reference} lists no nights")

    stays = runs(nights)
    for index, (checkin, checkout) in enumerate(stays):
        reservation = {
            "@context": "https://schema.org",
            "@type": "LodgingReservation",
            "reservationNumber": f"hostelworld-{reference}",
            "reservationStatus": "https://schema.org/ReservationConfirmed",
            "broker": {"@type": "Organization", "name": "Hostelworld"},
            "checkinTime": checkin.isoformat(),
            "checkoutTime": checkout.isoformat(),
            "reservationFor": hostel,
        }
        suffix = f"-{index + 1}" if len(stays) > 1 else ""
        Path(f"hostelworld-{reference}{suffix}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
