#!/usr/bin/env python3
"""FedEx parcel-tracking emails.

FedEx sends progress mails from TrackingUpdates@fedex.com and
noreply@fedex.com throughout a shipment:

- "We have your shipment NNNN."           -> label created
- "Your shipment is on the way NNNN"      -> in transit
- "Your shipment is out for delivery today NNNN"
                                          -> out for delivery
- "Your shipment was delivered NNNN"      -> delivered

The body always carries `Tracking ID NNNN` (12 or 15 digits). When out
for delivery, the body has `Estimated between Ham/pm and Ham/pm`
together with `Scheduled delivery date <Weekday>, DD/MM/YYYY` (or just
`today` - we use the message Date in that case). Delivered mails carry
`Delivery Date <Weekday>, DD/MM/YYYY H:MMam/pm`.

Emits a `.parcel.json` for each update. When a delivery window is
present, also emits a `.reservation.json` for the calendar slot.
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


TRACKING_RE = re.compile(r"Tracking\s+ID\s+(\d{12,15})", re.I)
SUBJECT_TRACKING_RE = re.compile(r"\b(\d{12,15})\b")
WINDOW_RE = re.compile(
    r"Estimated\s+between\s+"
    r"(\d{1,2}(?::\d{2})?(?:am|pm))\s+and\s+(\d{1,2}(?::\d{2})?(?:am|pm))",
    re.I,
)
SCHEDULED_DATE_RE = re.compile(
    r"Scheduled\s+delivery\s+date\s+[A-Z][a-z]+,?\s+(\d{1,2}/\d{1,2}/\d{4})",
    re.I,
)
DELIVERED_RE = re.compile(
    r"Delivery\s+Date\s+[A-Z][a-z]+,?\s+(\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(\d{1,2}(?::\d{2})?(?:am|pm))",
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


def parse_clock(s: str) -> tuple[int, int]:
    """Parse '9am' / '1:38pm' style time."""
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


def parse_date(date_str: str) -> datetime | None:
    try:
        return datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        return None


def status_from_subject(subject: str) -> str | None:
    s = subject.lower()
    if "was delivered" in s or "delivered" == s.split()[-1]:
        return "Delivered"
    if "out for delivery" in s:
        return "OutForDelivery"
    if "on the way" in s or "have your shipment" in s or "we have your shipment" in s:
        return "OnItsWay"
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
        # Some short variants fall back to the subject - but only trust a
        # numeric token if `tracking` is also mentioned somewhere in the
        # subject, otherwise we'd misclassify random numbers.
        if re.search(r"Tracking", mail.subject, re.I) or re.search(
            r"shipment.*\b\d{12,15}\b", mail.subject, re.I
        ):
            m = SUBJECT_TRACKING_RE.search(mail.subject)
            if m:
                tracking = m.group(1)
            else:
                return 0
        else:
            return 0
    else:
        tracking = tracking_match.group(1)

    status = status_from_subject(mail.subject)

    parcel = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "provider": {"@type": "Organization", "@id": "fedex", "name": "FedEx"},
    }
    if status:
        parcel["deliveryStatus"] = status

    window_start: datetime | None = None
    window_end: datetime | None = None

    if status == "OutForDelivery":
        win = WINDOW_RE.search(text)
        # The "today" mail rarely has the explicit scheduled-date; fall
        # back to the message Date for that case.
        date_m = SCHEDULED_DATE_RE.search(text)
        day = parse_date(date_m.group(1)) if date_m else None
        if day is None and mail.date is not None:
            day = mail.date.replace(tzinfo=None)
        if win and day is not None:
            sh, sm = parse_clock(win.group(1))
            eh, em = parse_clock(win.group(2))
            window_start = day.replace(hour=sh, minute=sm, second=0, microsecond=0)
            window_end = day.replace(hour=eh, minute=em, second=0, microsecond=0)
            parcel["expectedArrivalFrom"] = window_start.strftime("%Y-%m-%dT%H:%M:%S")
            parcel["expectedArrivalUntil"] = window_end.strftime("%Y-%m-%dT%H:%M:%S")
    elif status == "Delivered":
        d = DELIVERED_RE.search(text)
        if d:
            day = parse_date(d.group(1))
            if day is not None:
                h, mm = parse_clock(d.group(2))
                parcel["actualDeliveryTime"] = day.replace(hour=h, minute=mm).strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
    elif status == "OnItsWay":
        d = SCHEDULED_DATE_RE.search(text)
        if d:
            day = parse_date(d.group(1))
            if day is not None:
                parcel["expectedArrivalUntil"] = day.strftime("%Y-%m-%d")

    Path(f"fedex-{tracking}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )

    if window_start is not None and window_end is not None:
        reservation = {
            "@context": "https://schema.org",
            "@type": "EventReservation",
            "reservationNumber": f"fedex-delivery-{tracking}",
            "reservationFor": {
                "@type": "Event",
                "name": "FedEx delivery",
                "startDate": window_start.strftime("%Y-%m-%dT%H:%M:%S"),
                "endDate": window_end.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        Path(f"fedex-delivery-{tracking}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
