#!/usr/bin/env python3
"""Evri (formerly Hermes) parcel-tracking emails.

Evri sends notifications from do-not-reply@evri.com. The set of
templates we see in practice is narrow - mostly collection / handover /
delivery confirmations - and they all share the same body shape after
tag-stripping:

    Collection confirmation
    Your <merchant> parcel was collected from your selected ParcelShop
    on <Weekday> <D Month> at HH:MM.
    Tracking number
    H0000A0000000000

The tracking number lives on its own line after the literal "Tracking
number" label, and also appears in the tracking URL
(https://www.evri.com/track/parcel/<id>/details). The merchant comes
from the subject ("Thanks for collecting your <merchant> parcel")
falling back to the first paragraph in the body.
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


# Evri tracking numbers are alphanumeric, currently 16 characters.
TRACKING_RE = re.compile(r"\b([A-Z]\d{4}[A-Z]\d{10})\b")
URL_TRACKING_RE = re.compile(r"evri\.com/track/parcel/([A-Z0-9]{10,20})", re.I)
SUBJECT_COLLECTED_RE = re.compile(
    r"^Thanks\s+for\s+collecting\s+your\s+(?P<merchant>.+?)\s+parcel\s*$", re.I
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


def status_and_merchant(subject: str) -> tuple[str | None, str | None]:
    s = subject.strip()
    m = SUBJECT_COLLECTED_RE.match(s)
    if m:
        return "InTransit", m.group("merchant").strip()
    low = s.lower()
    if "has been delivered" in low or "successfully delivered" in low:
        return "Delivered", None
    if "out for delivery" in low:
        return "OutForDelivery", None
    if "on its way" in low or "is now with your local" in low:
        return "OnItsWay", None
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

    tracking_match = TRACKING_RE.search(text)
    if not tracking_match and mail.html:
        url_match = URL_TRACKING_RE.search(mail.html)
        if url_match:
            tracking = url_match.group(1)
        else:
            return 0
    elif tracking_match:
        tracking = tracking_match.group(1)
    else:
        return 0

    status, merchant = status_and_merchant(mail.subject)

    parcel = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "provider": {"@type": "Organization", "@id": "evri", "name": "Evri"},
    }
    if status:
        parcel["deliveryStatus"] = status
    if merchant:
        parcel["merchant"] = {"@type": "Organization", "name": merchant}

    Path(f"evri-{tracking}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
