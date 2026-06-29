#!/usr/bin/env python3
"""Parcelforce delivery-notification emails.

Parcelforce sends "Your parcel delivery" mails from
Notifications@parcelforce.co.uk shortly before the delivery window. The
plain-text rendering of the body is essentially one paragraph:

    Your parcel <id> from <merchant> is due to be delivered by <driver>
    of Parcelforce today between <HH:MM> and <HH:MM>.

The id is the JD-prefixed Royal Mail / Parcelforce shared tracking
number (variable length, leading "JD"). We treat any matching mail as
out-for-delivery and emit both a parcel record and a calendar
reservation for the window.
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


# JD-prefixed tracking number, alphanumeric tail.
TRACKING_RE = re.compile(r"\b(JD[A-Z0-9]{5,18})\b")
DELIVERY_RE = re.compile(
    r"Your\s+parcel\s+(?P<tracking>JD[A-Z0-9]{5,18})\s+from\s+(?P<merchant>.+?)\s+"
    r"is\s+due\s+to\s+be\s+delivered\b.*?between\s+(?P<start>\d{1,2}:\d{2})\s+"
    r"and\s+(?P<end>\d{1,2}:\d{2})",
    re.I | re.S,
)


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


def main() -> int:
    mail = read_message()
    if not mail.html and not mail.text:
        return 0
    text = strip_html(mail.html) if mail.html else mail.text or ""

    m = DELIVERY_RE.search(text)
    if not m:
        # Fall back to picking up just the tracking number for any
        # other Parcelforce notification we haven't profiled yet.
        t = TRACKING_RE.search(text)
        if not t:
            return 0
        parcel = {
            "@context": "https://schema.org",
            "@type": "ParcelDelivery",
            "trackingNumber": t.group(1),
            "provider": {
                "@type": "Organization",
                "@id": "parcelforce",
                "name": "Parcelforce",
            },
        }
        Path(f"parcelforce-{t.group(1)}.parcel.json").write_text(
            json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
        )
        return 0

    tracking = m.group("tracking")
    merchant = m.group("merchant").strip()
    sh, sm = (int(x) for x in m.group("start").split(":"))
    eh, em = (int(x) for x in m.group("end").split(":"))

    if mail.date is None:
        return 0
    day = mail.date.replace(tzinfo=None)
    window_start = day.replace(hour=sh, minute=sm, second=0, microsecond=0)
    window_end = day.replace(hour=eh, minute=em, second=0, microsecond=0)

    parcel = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "deliveryStatus": "OutForDelivery",
        "provider": {
            "@type": "Organization",
            "@id": "parcelforce",
            "name": "Parcelforce",
        },
        "merchant": {"@type": "Organization", "name": merchant},
        "expectedArrivalFrom": window_start.strftime("%Y-%m-%dT%H:%M:%S"),
        "expectedArrivalUntil": window_end.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    Path(f"parcelforce-{tracking}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )

    reservation = {
        "@context": "https://schema.org",
        "@type": "EventReservation",
        "reservationNumber": f"parcelforce-delivery-{tracking}",
        "reservationFor": {
            "@type": "Event",
            "name": "Parcelforce delivery",
            "startDate": window_start.strftime("%Y-%m-%dT%H:%M:%S"),
            "endDate": window_end.strftime("%Y-%m-%dT%H:%M:%S"),
        },
    }
    Path(f"parcelforce-delivery-{tracking}.reservation.json").write_text(
        json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
