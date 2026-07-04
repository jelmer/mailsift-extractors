#!/usr/bin/env python3
"""DPD parcel-tracking emails.

DPD sends mails at three stages of a parcel's life:

- "We're expecting your <X> parcel"      -> incoming, ETA not yet set
- "Your <X> parcel is on its way"        -> in transit (less common)
- "Your <X> order will be delivered today between H:MM - H:MM"
  -> out for delivery with a window

The body always carries the tracking number formatted with spaces
("1500 0000 000 000"). We strip the spaces for the on-disk identifier
so it matches what the DPD website would show.

Like Royal Mail, we emit a `.parcel.json` for every update so the
parcels target can merge them by tracking number, and a
`.reservation.json` only when a delivery window is present.
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


TRACKING_RE = re.compile(r"Your parcel:\s*(\d{4}\s\d{4}\s\d{3}\s\d{3})")
# "TODAY 9th February 2026 between 13:40 - 14:40"
WINDOW_RE = re.compile(
    r"TODAY\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Z][a-z]+)\s+(\d{4})\s+between\s+"
    r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})",
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


def status_from_subject(subject: str) -> str | None:
    s = subject.lower()
    if "will be delivered today" in s:
        return "OutForDelivery"
    if "on its way" in s:
        return "OnItsWay"
    if "expecting your" in s and "parcel" in s:
        return "Scheduled"
    return None


def main() -> int:
    mail = read_message()
    if not mail.html or not mail.subject:
        return 0

    text = strip_html(mail.html)

    tracking_match = TRACKING_RE.search(text)
    if not tracking_match:
        return 0
    # Strip the spaces so the parcels target keys on a single token.
    tracking = re.sub(r"\s+", "", tracking_match.group(1))

    status = status_from_subject(mail.subject)

    parcel = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "provider": {"@type": "Organization", "@id": "dpd", "name": "DPD"},
    }
    if status:
        parcel["deliveryStatus"] = status

    window_start: datetime | None = None
    window_end: datetime | None = None
    if status == "OutForDelivery":
        m = WINDOW_RE.search(text)
        if m:
            day = int(m.group(1))
            month_name = m.group(2).lower()
            year = int(m.group(3))
            if month_name in MONTHS:
                month = MONTHS[month_name]
                sh, sm = (int(x) for x in m.group(4).split(":"))
                eh, em = (int(x) for x in m.group(5).split(":"))
                window_start = datetime(year, month, day, sh, sm)
                window_end = datetime(year, month, day, eh, em)
                parcel["expectedArrivalFrom"] = window_start.strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
                parcel["expectedArrivalUntil"] = window_end.strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )

    Path(f"dpd-{tracking}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )

    if window_start is not None and window_end is not None:
        reservation = {
            "@context": "https://schema.org",
            "@type": "EventReservation",
            "reservationNumber": f"dpd-delivery-{tracking}",
            "reservationFor": {
                "@type": "Event",
                "name": "DPD delivery",
                "startDate": window_start.strftime("%Y-%m-%dT%H:%M:%S"),
                "endDate": window_end.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        Path(f"dpd-delivery-{tracking}.reservation.json").write_text(
            json.dumps(reservation, ensure_ascii=False), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
