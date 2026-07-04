#!/usr/bin/env python3
"""Royal Mail parcel-tracking emails.

Royal Mail sends four mails as a parcel progresses:

- "Your Royal Mail parcel is on its way" -> in transit
- "Your Royal Mail parcel is due to be delivered" -> scheduled
- "Your Royal Mail parcel is due to be delivered today" -> out for
  delivery with a time window
- "Your Royal Mail parcel has been delivered ..." -> delivered

Each mail carries the 13-character tracking number ([A-Z]{2}\\d{9,11}[A-Z]{2})
near the bottom. The "due to be delivered today" mail additionally has a
human-readable date and time window in the body.

Emits a `.parcel.json` for every status update, so the parcels target
can merge them into a single record per tracking number. When a time
window is present, also emits a `.reservation.json` so the delivery
slot shows up on the calendar.
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


TRACKING_RE = re.compile(r"\b([A-Z]{2}\d{9,11}[A-Z]{2})\b")
DATE_RE = re.compile(
    r"Today,?\s*([A-Z][a-z]+),?\s*(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})",
    re.I,
)
WINDOW_RE = re.compile(
    r"estimated between:?\s*(\d{1,2}(?::\d{2})?(?:am|pm))\s+and\s+(\d{1,2}(?::\d{2})?(?:am|pm))",
    re.I,
)

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


def parse_clock(s: str) -> tuple[int, int]:
    """Parse '11am' / '12:30pm' style time."""
    m = re.match(r"(\d{1,2})(?::(\d{2}))?(am|pm)", s, re.I)
    if not m:
        raise ValueError(f"bad time {s!r}")
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    suffix = m.group(3).lower()
    if suffix == "pm" and hour != 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    return hour, minute


def status_from_subject(subject: str) -> str | None:
    s = subject.lower()
    # Check "due to be delivered today" before any "delivered ..." match -
    # "delivered today" otherwise looks like "delivered to..." and gets
    # misclassified.
    if "due to be delivered today" in s:
        return "OutForDelivery"
    if "due to be delivered" in s:
        return "Scheduled"
    if "has been delivered" in s or "delivered to your" in s:
        return "Delivered"
    if "on its way" in s:
        return "OnItsWay"
    return None


def main() -> int:
    mail = read_message()
    if not mail.html or not mail.subject:
        return 0

    text = strip_html(mail.html)

    tracking_match = TRACKING_RE.search(text)
    if not tracking_match:
        return 0
    tracking = tracking_match.group(1)

    status = status_from_subject(mail.subject)

    parcel = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "provider": {
            "@type": "Organization",
            "@id": "royal-mail",
            "name": "Royal Mail",
        },
    }
    if status:
        parcel["deliveryStatus"] = status

    # If this is the "out for delivery today" mail, pull the window and
    # add it to the parcel record and also emit a calendar event.
    window_start: datetime | None = None
    window_end: datetime | None = None
    if status == "OutForDelivery":
        date_m = DATE_RE.search(text)
        window_m = WINDOW_RE.search(text)
        if date_m and window_m:
            day = int(date_m.group(2))
            month_name = date_m.group(3).lower()
            year = int(date_m.group(4))
            if month_name in MONTHS:
                month = MONTHS[month_name]
                sh, sm = parse_clock(window_m.group(1))
                eh, em = parse_clock(window_m.group(2))
                window_start = datetime(year, month, day, sh, sm)
                window_end = datetime(year, month, day, eh, em)
                parcel["expectedArrivalFrom"] = window_start.strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
                parcel["expectedArrivalUntil"] = window_end.strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )

    Path(f"royalmail-{tracking}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )

    if window_start is not None and window_end is not None:
        reservation = {
            "@context": "https://schema.org",
            "@type": "EventReservation",
            "reservationNumber": f"royalmail-delivery-{tracking}",
            "reservationFor": {
                "@type": "Event",
                "name": "Royal Mail delivery",
                "startDate": window_start.strftime("%Y-%m-%dT%H:%M:%S"),
                "endDate": window_end.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        Path(f"royalmail-delivery-{tracking}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
