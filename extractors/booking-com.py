#!/usr/bin/env python3
"""Booking.com hotel reservation confirmations.

These don't carry schema.org markup, but their HTML is consistent
enough across years to scrape directly. We pull confirmation number,
check-in / check-out date+time, location, and hotel name (from
subject), and emit a single `LodgingReservation` for the stay.
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


SUBJECT_HOTEL_RE = re.compile(
    r"(?:Thanks!?|booking)\s*Your booking is confirmed at\s+(.+)$", re.I
)
SUBJECT_HOTEL_RE_LOOSE = re.compile(r"confirmed at\s+(.+?)(?:$|\s*\(from)", re.I)

CONFIRMATION_RE = re.compile(r"Confirmation:\s*(\d+)")

# Booking.com renders dates a few ways across years and locales. We hand
# the leading-day-of-week chunk to strptime, trying each format in turn.
DATE_FORMATS = [
    "%A, %d %B %Y",  # "Friday, 27 December 2024"
    "%A, %B %d, %Y",  # "Saturday, July 20, 2024"
    "%A %d %B %Y",  # "Tuesday 23 July 2024"
    "%a %d %b %Y",  # "Tue 23 Jul 2024"
]

CHECKIN_RE = re.compile(
    r"Check-in\s+([A-Z][a-z]+(?:,)?\s+(?:[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Z][a-z]+\s+\d{4}))"
    r"\s*\((?:from\s+)?(\d{1,2}:\d{2})",
)
CHECKOUT_RE = re.compile(
    r"Check-out\s+([A-Z][a-z]+(?:,)?\s+(?:[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Z][a-z]+\s+\d{4}))"
    r"\s*\((?:until\s+)?(\d{1,2}:\d{2})",
)
LOCATION_RE = re.compile(r"Location\s+([^P]+?)\s+Phone\b", re.S)


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(html: str) -> str:
    p = _Strip()
    p.feed(html)
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()


def parse_date(s: str) -> datetime | None:
    s = s.strip().replace(",", " ").replace("  ", " ").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt.replace(",", "").replace("  ", " "))
        except ValueError:
            continue
    return None


def parse_check(text: str, regex: re.Pattern[str]) -> datetime | None:
    m = regex.search(text)
    if not m:
        return None
    date_str, time_str = m.group(1), m.group(2)
    date = parse_date(date_str)
    if date is None:
        return None
    hh, mm = (int(x) for x in time_str.split(":"))
    return date.replace(hour=hh, minute=mm)


def hotel_from_subject(subject: str | None) -> str | None:
    if not subject:
        return None
    subject = subject.strip()
    m = SUBJECT_HOTEL_RE.search(subject)
    if m:
        return m.group(1).strip()
    m = SUBJECT_HOTEL_RE_LOOSE.search(subject)
    if m:
        return m.group(1).strip()
    return None


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html)

    confirmation = None
    m = CONFIRMATION_RE.search(text)
    if m:
        confirmation = m.group(1)

    checkin = parse_check(text, CHECKIN_RE)
    checkout = parse_check(text, CHECKOUT_RE)
    if checkin is None or checkout is None:
        return 0

    hotel = hotel_from_subject(mail.subject) or "Hotel"

    location = None
    m = LOCATION_RE.search(text)
    if m:
        location = re.sub(r"\s+", " ", m.group(1)).strip()

    reservation: dict = {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "checkinTime": checkin.strftime("%Y-%m-%dT%H:%M:%S"),
        "checkoutTime": checkout.strftime("%Y-%m-%dT%H:%M:%S"),
        "reservationFor": {
            "@type": "LodgingBusiness",
            "name": hotel,
        },
    }
    if confirmation:
        reservation["reservationNumber"] = f"booking-com-{confirmation}"
    if location:
        reservation["reservationFor"]["address"] = location

    slug_basis = confirmation or hotel
    slug = re.sub(r"[^A-Za-z0-9_.+-]+", "-", slug_basis).strip("-") or "booking"
    Path(f"booking-com-{slug}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
