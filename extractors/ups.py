#!/usr/bin/env python3
"""UPS parcel-tracking emails.

UPS sends notifications from pkginfo@ups.com (initial shipment) and
mcinfo@ups.com (My Choice updates: out-for-delivery and delivered).
After tag-stripping the HTML the relevant text is in a stable form:

- "Estimated Delivery Date: <Weekday>, DD/MM/YYYY"        -> shipped
- "Estimated Delivery <Weekday> DD/MM/YYYY between HH:MM - HH:MM"
                                                          -> out for delivery
- "Delivered <Weekday> DD/MM/YYYY HH:MM"                  -> delivered
- "Tracking Number: 1Zxxxxxxxxxxxxxxxxx" or service line `UPS <X>
  1Zxxxx...` carry the 18-character 1Z tracking id.

Emits a `.parcel.json` for each update. When a delivery window is
present, also emits a `.reservation.json` so the slot lands on the
calendar.
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


TRACKING_RE = re.compile(r"\b(1Z[A-Z0-9]{16})\b")
WINDOW_RE = re.compile(
    r"Estimated\s+Delivery\s+[A-Z][a-z]+,?\s+"
    r"(?P<date>\d{2}/\d{2}/\d{4})\s+between\s+"
    r"(?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})",
    re.I,
)
DELIVERED_RE = re.compile(
    r"Delivered\s+[A-Z][a-z]+,?\s+(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<time>\d{1,2}:\d{2})",
    re.I,
)
SCHEDULED_DATE_RE = re.compile(
    r"Estimated\s+Delivery\s+Date:?\s*[A-Z][a-z]+,?\s+(?P<date>\d{2}/\d{2}/\d{4})",
    re.I,
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


def status_from_subject(subject: str) -> str | None:
    s = subject.lower()
    if "was delivered" in s or "parcel delivered" in s:
        return "Delivered"
    if (
        "scheduled for delivery" in s
        or "arriving tomorrow" in s
        or "out for delivery" in s
    ):
        return "OutForDelivery"
    if "shipping notification" in s or "has been shipped" in s or "on the way" in s:
        return "OnItsWay"
    return None


def parse_date(date_str: str) -> datetime | None:
    try:
        return datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        return None


def main() -> int:
    mail = read_message()
    if not mail.subject:
        return 0

    if mail.html:
        text = strip_html(mail.html)
    elif mail.text:
        text = mail.text
    else:
        return 0

    tracking_match = TRACKING_RE.search(text)
    if not tracking_match:
        return 0
    tracking = tracking_match.group(1)

    status = status_from_subject(mail.subject)

    parcel = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "provider": {"@type": "Organization", "@id": "ups", "name": "UPS"},
    }
    if status:
        parcel["deliveryStatus"] = status

    window_start: datetime | None = None
    window_end: datetime | None = None

    if status == "OutForDelivery":
        m = WINDOW_RE.search(text)
        if m:
            day = parse_date(m.group("date"))
            if day is not None:
                sh, sm = (int(x) for x in m.group("start").split(":"))
                eh, em = (int(x) for x in m.group("end").split(":"))
                window_start = day.replace(hour=sh, minute=sm)
                window_end = day.replace(hour=eh, minute=em)
                parcel["expectedArrivalFrom"] = window_start.strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
                parcel["expectedArrivalUntil"] = window_end.strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
    elif status == "Delivered":
        m = DELIVERED_RE.search(text)
        if m:
            day = parse_date(m.group("date"))
            if day is not None:
                h, mm = (int(x) for x in m.group("time").split(":"))
                parcel["actualDeliveryTime"] = day.replace(hour=h, minute=mm).strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
    else:
        # Initial shipping notification: include just the date.
        m = SCHEDULED_DATE_RE.search(text)
        if m:
            day = parse_date(m.group("date"))
            if day is not None:
                parcel["expectedArrivalUntil"] = day.strftime("%Y-%m-%d")

    Path(f"ups-{tracking}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )

    if window_start is not None and window_end is not None:
        reservation = {
            "@context": "https://schema.org",
            "@type": "EventReservation",
            "reservationNumber": f"ups-delivery-{tracking}",
            "reservationFor": {
                "@type": "Event",
                "name": "UPS delivery",
                "startDate": window_start.strftime("%Y-%m-%dT%H:%M:%S"),
                "endDate": window_end.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        Path(f"ups-delivery-{tracking}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
