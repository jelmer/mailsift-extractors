#!/usr/bin/env python3
"""Booking.com hotel confirmations from before schema.org markup.

Until late January 2015 Booking.com titled its confirmations "Your
booking at <property>" and sent them without JSON-LD. The HTML went
through a few layouts between 2013 and 2015, but every one of them
renders as label lines ("Booking number", "Check-in:", "Address:",
...) each followed by the value, so we walk the stripped body line by
line rather than scraping the markup.

The same template carried JSON-LD from late January 2015 on; those
mails are left to the generic schema-ld extractor.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

SUBJECT_RE = re.compile(r"^Your booking at (.+)$", re.IGNORECASE)

DATE_FORMATS = [
    "%A, %d %B %Y",  # "Wednesday, 9 January 2013"
    "%A, %B %d, %Y",  # "Monday, January 5, 2015"
]

TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Direction marks Booking.com appends after the guest's email address.
BIDI_RE = re.compile(r"[\u200e\u200f]")
# "Mountain View (California)": the region rides along with the town.
LOCALITY_REGION_RE = re.compile(r"^(.+?)\s*\((.+)\)$")


def label_index(lines: list[str], label: str, start: int = 0) -> int | None:
    pattern = re.compile(rf"^{label}:?$", re.IGNORECASE)
    for i in range(start, len(lines)):
        if pattern.match(lines[i]):
            return i
    return None


def parse_check(lines: list[str], label: str, *, last_time: bool) -> str:
    i = label_index(lines, label)
    if i is None or i + 1 >= len(lines):
        raise ValueError(f"no {label} line")
    date_str = lines[i + 1]
    for fmt in DATE_FORMATS:
        try:
            date = datetime.strptime(date_str, fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"unrecognised {label} date {date_str!r}")
    # The next line holds the hours: "(from 14:00)", "(until 11:00)",
    # or a window like "(12:00 - 23:00)". Arrival is the start of the
    # window, departure its end.
    times = TIME_RE.findall(lines[i + 2]) if i + 2 < len(lines) else []
    if not times:
        return date.strftime("%Y-%m-%d")
    hh, mm = times[-1] if last_time else times[0]
    return date.replace(hour=int(hh), minute=int(mm)).strftime("%Y-%m-%dT%H:%M:%S")


def postal_address(lines: list[str]) -> dict | str:
    """Structure the lines between "Address:" and "Phone:".

    The block ends in "<town>, <postcode>" followed by the country on
    its own line; anything before is street. Properties abroad may
    append the address again in local script, so the country is the
    last digit- and comma-free line that follows a "<town>, ..." line.
    """
    country_idx = None
    for i in range(1, len(lines)):
        if not re.search(r"[\d,]", lines[i]) and "," in lines[i - 1]:
            country_idx = i
    if country_idx is None:
        return ", ".join(lines)

    town, _, postcode = lines[country_idx - 1].partition(",")
    town = town.strip()
    postcode = postcode.strip().rstrip(",").strip()
    address: dict = {"@type": "PostalAddress"}
    street = ", ".join(lines[: country_idx - 1])
    if street:
        address["streetAddress"] = street
    m = LOCALITY_REGION_RE.match(town)
    if m:
        address["addressLocality"] = m.group(1)
        address["addressRegion"] = m.group(2)
    else:
        address["addressLocality"] = town
    if postcode:
        address["postalCode"] = postcode
    address["addressCountry"] = lines[country_idx]
    return address


def under_name(lines: list[str], start: int) -> dict | None:
    i = label_index(lines, "Booked by", start)
    if i is None or i + 1 >= len(lines):
        return None
    booked_by = BIDI_RE.sub("", lines[i + 1])
    person: dict = {"@type": "Person"}
    m = EMAIL_RE.search(booked_by)
    if m:
        name = booked_by[: m.start()].strip().rstrip("(").strip()
        email = m.group(0)
    else:
        # The 2013 layout gives the guest's email its own label just
        # above "Booked by".
        name = booked_by.strip()
        email = None
        j = label_index(lines, "E-?mail", start)
        if j is not None and j < i and j + 1 < len(lines):
            email = lines[j + 1]
    person["name"] = name
    if email:
        person["email"] = email
    return person


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    if mail.ld_json:
        # From late January 2015 on the same mail carries JSON-LD and
        # schema-ld files it; emitting here as well would duplicate it.
        return 0
    m = SUBJECT_RE.match((mail.subject or "").strip())
    if not m:
        return 0
    hotel = m.group(1).strip()

    lines = [
        line.strip()
        for line in strip_html(mail.html, block_tags=True).splitlines()
        if line.strip()
    ]

    i = label_index(lines, "Booking number")
    if i is None or i + 1 >= len(lines) or not lines[i + 1].isdigit():
        raise ValueError("no booking number")
    booking_number = lines[i + 1]

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationNumber": f"booking-com-{booking_number}",
        "checkinTime": parse_check(lines, "Check-in", last_time=False),
        "checkoutTime": parse_check(lines, "Check-out", last_time=True),
        "reservationFor": {"@type": "LodgingBusiness", "name": hotel},
    }

    a = label_index(lines, "Address")
    if a is not None:
        p = label_index(lines, "Phone", a + 1)
        if p is None:
            raise ValueError("address block without a phone line")
        reservation["reservationFor"]["address"] = postal_address(lines[a + 1 : p])
        if p + 1 < len(lines):
            reservation["reservationFor"]["telephone"] = lines[p + 1]

    person = under_name(lines, i)
    if person:
        reservation["underName"] = person

    Path(f"booking-com-{booking_number}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
