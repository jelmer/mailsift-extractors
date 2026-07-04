#!/usr/bin/env python3
"""Sainsbury's grocery delivery slot confirmation emails.

Each "Your delivery will arrive between H:MMam - H:MMpm" mail carries
the slot in the body as

    <Weekday> <Day> <Month>, H:MMam - H:MMpm to <POSTCODE>

with the order number a few lines down. The year is not in the body,
but the mail is sent the night before delivery, so the message Date
gives it.

We emit an EventReservation for the delivery window, UID-keyed off the
order number so a follow-up "we got your changes" mail with the same
order number replaces the existing event in place.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


SLOT_RE = re.compile(
    r"(?P<weekday>Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\s+"
    r"(?P<day>\d{1,2})\s+(?P<month>[A-Z][a-z]+)"
    r",\s*"
    r"(?P<start>\d{1,2}:\d{2}(?:am|pm))\s*-\s*(?P<end>\d{1,2}:\d{2}(?:am|pm))"
    # UK postcode: 1-2 letters, 1-2 digits, optional letter, then space,
    # then 1 digit, 2 letters.
    r"\s+to\s+(?P<postcode>[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})",
    re.I,
)
ORDER_RE = re.compile(r"Order number:\s*(\d+)")

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


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


def parse_clock(time_str: str) -> tuple[int, int]:
    s = time_str.strip().lower()
    suffix = s[-2:]
    h, m = s[:-2].split(":")
    hour = int(h)
    minute = int(m)
    if suffix == "pm" and hour != 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    return hour, minute


def resolve_year(message_date: datetime | None, day: int, month: int) -> int:
    """Pick the year that places the slot closest to the message date."""
    if message_date is None:
        return datetime.now(timezone.utc).year
    candidates = [
        datetime(message_date.year - 1, month, day),
        datetime(message_date.year, month, day),
        datetime(message_date.year + 1, month, day),
    ]
    ref = message_date.replace(tzinfo=None)
    candidates.sort(key=lambda d: abs((d - ref).days))
    return candidates[0].year


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0

    text = strip_html(mail.html)
    slot = SLOT_RE.search(text)
    if not slot:
        return 0

    month_name = slot.group("month").lower()
    if month_name not in MONTHS:
        return 0
    month = MONTHS[month_name]
    day = int(slot.group("day"))

    start_h, start_m = parse_clock(slot.group("start"))
    end_h, end_m = parse_clock(slot.group("end"))

    year = resolve_year(mail.date, day, month)
    dtstart = datetime(year, month, day, start_h, start_m)
    dtend = datetime(year, month, day, end_h, end_m)
    if dtend < dtstart:
        dtend += timedelta(days=1)

    order = ORDER_RE.search(text)
    order_id = order.group(1) if order else None

    postcode = slot.group("postcode").strip()

    reservation = {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationFor": {
            "@type": "Event",
            "name": "Sainsbury's delivery",
            "startDate": dtstart.strftime("%Y-%m-%dT%H:%M:%S"),
            "endDate": dtend.strftime("%Y-%m-%dT%H:%M:%S"),
            "location": {
                "@type": "Place",
                "address": postcode,
            },
        },
    }
    if order_id:
        reservation["reservationNumber"] = f"sainsburys-{order_id}"

    slug_basis = order_id or dtstart.date().isoformat()
    Path(f"sainsburys-{slug_basis}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
