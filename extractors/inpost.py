#!/usr/bin/env python3
"""InPost (UK) mails about a parcel you are sending.

InPost writes to the sender at each step of a locker-to-locker parcel,
so these are all filed as outgoing (`mailsift:direction`):

- "Your QR code is ready" -> label bought, not yet dropped off
- "Your parcel is locker-ed up" -> dropped off
- "Your parcel is heading their way" -> picked up from the drop-off
- "It's ready for them to collect" -> waiting in the recipient's locker,
  which counts as out for delivery, as doorstep has it for DPD
- "It's been collected" -> collected by the recipient, with a
  "Collection date" of DD/MM/YYYY HH:MM

The JJD tracking number appears in every one of them. Mail to the
recipient of an InPost parcel has different subjects and is not
handled here.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

TRACKING_RE = re.compile(r"\b(JJD\d{10,})\b")
COLLECTED_RE = re.compile(r"Collection date\s+(\d{2}/\d{2}/\d{4} \d{2}:\d{2})")
_APOSTROPHE = "['’]"
SUBJECT_STATUSES = [
    (re.compile(r"^Your QR code is ready\b", re.IGNORECASE), "Scheduled"),
    (re.compile(r"^Your parcel is locker-ed up\b", re.IGNORECASE), "OnItsWay"),
    (re.compile(r"^Your parcel is heading their way\b", re.IGNORECASE), "OnItsWay"),
    (
        re.compile(rf"^It{_APOSTROPHE}s ready for them to collect\b", re.IGNORECASE),
        "OutForDelivery",
    ),
    (re.compile(rf"^It{_APOSTROPHE}s been collected\b", re.IGNORECASE), "Delivered"),
]


def status_from_subject(subject: str) -> str | None:
    for pattern, status in SUBJECT_STATUSES:
        if pattern.match(subject.strip()):
            return status
    return None


def main() -> int:
    mail = read_message()
    if not mail.html or not mail.subject:
        return 0
    status = status_from_subject(mail.subject)
    if status is None:
        return 0
    text = strip_html(mail.html, spaced=True)
    tracking_m = TRACKING_RE.search(text)
    if not tracking_m:
        return 0
    tracking = tracking_m.group(1)

    parcel: dict = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "provider": {"@type": "Organization", "@id": "inpost", "name": "InPost"},
        "deliveryStatus": status,
        "mailsift:direction": "outgoing",
    }
    if status == "Delivered":
        collected_m = COLLECTED_RE.search(text)
        if collected_m:
            collected = datetime.strptime(collected_m.group(1), "%d/%m/%Y %H:%M")
            parcel["actualDeliveryTime"] = collected.strftime("%Y-%m-%dT%H:%M:%S")

    Path(f"inpost-{tracking}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
