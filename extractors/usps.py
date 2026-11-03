#!/usr/bin/env python3
"""USPS Tracking notification emails.

USPS mails a notification per tracking event from
auto-reply@tracking.usps.com. The subject names the event and ends in
the tracking number:

    USPS® Item Delivered, Parcel Locker 9400100000000000000000
    USPS® Item Out for Delivery 9400100000000000000000

After tag-stripping, the body carries the same number after
`Tracking Number:`, the delivery moment for a delivered item
("... delivered to a parcel locker at 1:02 pm on November 1, 2026 in
CITY, ST 00000") and the shipper ("Package Shipped from: <NAME>").

Emits a `.parcel.json` keyed by the tracking number; mailsift merges
the updates for one parcel into a single record. The delivery address
is not recorded.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

# USPS numbers are 20-22 digits for domestic labels, or the 13-character
# international form (two letters, nine digits, US).
TRACKING_RE = re.compile(r"\b(\d{20,22}|[A-Z]{2}\d{9}US)\b")
BODY_TRACKING_RE = re.compile(r"Tracking Number:\s*([A-Z0-9]{13,34})", re.IGNORECASE)
DELIVERED_AT_RE = re.compile(
    r"delivered\b.*?\bat\s+(?P<time>\d{1,2}:\d{2}\s*[ap]\.?m\.?)\s+on\s+"
    r"(?P<date>[A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
    re.IGNORECASE,
)
SHIPPER_RE = re.compile(
    r"Package Shipped from:\s*(?P<shipper>[^\n]+?)\s*(?:$|\n)", re.MULTILINE
)

# Subject phrase -> canonical delivery status, most final first.
SUBJECT_TO_STATUS = [
    ("delivered", "Delivered"),
    ("out for delivery", "OutForDelivery"),
    ("expected delivery", "OnItsWay"),
    ("in transit", "InTransit"),
]


def status_from_subject(subject: str) -> str | None:
    s = subject.lower()
    for needle, status in SUBJECT_TO_STATUS:
        if needle in s:
            return status
    return None


def parse_delivered_at(text: str) -> str | None:
    m = DELIVERED_AT_RE.search(text)
    if not m:
        return None
    clock = m.group("time").replace(".", "").replace(" ", "").upper()
    try:
        moment = datetime.strptime(f"{m.group('date')} {clock}", "%B %d, %Y %I:%M%p")
    except ValueError:
        return None
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def main() -> int:
    mail = read_message()
    subject = mail.subject or ""
    if not mail.html:
        return 0
    text = strip_html(mail.html, block_tags=True)

    m = BODY_TRACKING_RE.search(text) or TRACKING_RE.search(subject)
    if not m:
        return 0
    tracking = m.group(1).upper()

    parcel: dict = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "trackingUrl": f"https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking}",
        "provider": {"@type": "Organization", "@id": "usps", "name": "USPS"},
    }
    status = status_from_subject(subject)
    if status:
        parcel["deliveryStatus"] = status
    if status == "Delivered":
        delivered = parse_delivered_at(text)
        if delivered:
            parcel["actualDeliveryTime"] = delivered
    shipper = SHIPPER_RE.search(text)
    if shipper:
        parcel["merchant"] = shipper.group("shipper").strip()

    Path(f"usps-{tracking}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
