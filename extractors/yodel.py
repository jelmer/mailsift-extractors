#!/usr/bin/env python3
"""Yodel parcel-tracking emails.

Yodel sends three notifications from noreply@yodel.co.uk:

- "Not long to wait now"                  -> in transit
- "Your <merchant> parcel is out for delivery"
                                          -> out for delivery, with HH:MM - HH:MM window
- "Rate your delivery"                    -> delivered (often with safe-place note)

The tracking number is the JD-prefixed code, present both in the body
text ("Your tracking number: JD...") and the tracking URL
(http://yodel.co.uk/tracking/<JD...>). Delivery-window mails include
the merchant name in the subject ("Your <merchant> parcel is out for
delivery") and the time range on its own line in the body.

Emits a `.parcel.json` for every update; on out-for-delivery also emits
a `.reservation.json` so the slot lands on the calendar. The merchant
is parsed from the subject (or body) when available.
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


TRACKING_RE = re.compile(r"\b(JD\d{15,20})\b")
WINDOW_RE = re.compile(r"\b(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\b")
OUT_FOR_DELIVERY_RE = re.compile(
    r"^Your\s+(?P<merchant>.+?)\s+parcel\s+is\s+out\s+for\s+delivery\s*$", re.I
)
ON_ITS_WAY_BODY_RE = re.compile(r"Your\s+(.+?)\s+parcel\s+is\s+on\s+its\s+way", re.I)


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


def status_and_merchant(subject: str, body: str) -> tuple[str | None, str | None]:
    m = OUT_FOR_DELIVERY_RE.match(subject)
    if m:
        return "OutForDelivery", m.group("merchant").strip()
    s = subject.lower()
    if "not long to wait" in s or "on its way" in s:
        wm = ON_ITS_WAY_BODY_RE.search(body)
        merchant = wm.group(1).strip() if wm else None
        return "OnItsWay", merchant
    if "rate your delivery" in s or "delivered" in s:
        return "Delivered", None
    return None, None


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

    # Try the visible text first; some templates only expose the tracking
    # number in the href of the "Track parcel" link, so fall back to the
    # raw HTML if we didn't find it.
    tracking_match = TRACKING_RE.search(text)
    if not tracking_match and mail.html:
        tracking_match = TRACKING_RE.search(mail.html)
    if not tracking_match:
        return 0
    tracking = tracking_match.group(1)

    status, merchant = status_and_merchant(mail.subject.strip(), text)

    parcel = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "provider": {"@type": "Organization", "@id": "yodel", "name": "Yodel"},
    }
    if status:
        parcel["deliveryStatus"] = status
    if merchant:
        parcel["merchant"] = {"@type": "Organization", "name": merchant}

    window_start: datetime | None = None
    window_end: datetime | None = None

    if status == "OutForDelivery":
        wm = WINDOW_RE.search(text)
        if wm and mail.date is not None:
            sh, sm = (int(x) for x in wm.group(1).split(":"))
            eh, em = (int(x) for x in wm.group(2).split(":"))
            day = mail.date.replace(tzinfo=None)
            window_start = day.replace(hour=sh, minute=sm, second=0, microsecond=0)
            window_end = day.replace(hour=eh, minute=em, second=0, microsecond=0)
            parcel["expectedArrivalFrom"] = window_start.strftime("%Y-%m-%dT%H:%M:%S")
            parcel["expectedArrivalUntil"] = window_end.strftime("%Y-%m-%dT%H:%M:%S")

    Path(f"yodel-{tracking}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )

    if window_start is not None and window_end is not None:
        reservation = {
            "@context": "https://schema.org",
            "@type": "EventReservation",
            "reservationNumber": f"yodel-delivery-{tracking}",
            "reservationFor": {
                "@type": "Event",
                "name": "Yodel delivery",
                "startDate": window_start.strftime("%Y-%m-%dT%H:%M:%S"),
                "endDate": window_end.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        Path(f"yodel-delivery-{tracking}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
