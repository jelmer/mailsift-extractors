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

"UPS Label Delivery" mails are for a parcel you are sending: they are
filed as outgoing (`mailsift:direction`) with the "Ship To:" name as
the recipient. "UPS Collection Request" mails carry only a collection
number, not a tracking number, so they are left alone.

Emits a `.parcel.json` for each update. The delivery window rides on
the same file (`expectedArrivalFrom`/`Until`) when present - a parcel
isn't a reservation, so no separate calendar artifact is written.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

TRACKING_RE = re.compile(r"\b(1Z[A-Z0-9]{16})\b")
WINDOW_RE = re.compile(
    r"Estimated\s+Delivery\s+[A-Z][a-z]+,?\s+"
    r"(?P<date>\d{2}/\d{2}/\d{4})\s+between\s+"
    r"(?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})",
    re.IGNORECASE,
)
DELIVERED_RE = re.compile(
    r"Delivered\s+[A-Z][a-z]+,?\s+(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<time>\d{1,2}:\d{2})",
    re.IGNORECASE,
)
SCHEDULED_DATE_RE = re.compile(
    r"Estimated\s+Delivery\s+Date:?\s*[A-Z][a-z]+,?\s+(?P<date>\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)


def status_from_subject(subject: str) -> str | None:
    s = subject.lower()
    if (
        "was delivered" in s
        or "parcel delivered" in s
        or "delivery notification" in s
        or "afleveringsbevestiging" in s
    ):
        return "Delivered"
    if "exception notification" in s:
        return "OrderProblem"
    # Waiting at an Access Point counts as out for delivery, as mailroom
    # has it for DPD.
    if "ready for collection" in s:
        return "OutForDelivery"
    if "ship notification" in s or "verzendbericht" in s:
        return "OnItsWay"
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


SENDER_RE = re.compile(r"^\s*From:? (\S.*?)\s*$", re.MULTILINE)
# My Choice mails before about 2023 have the shipper in capitals on the
# line above the tracking number: `THOMANN GMBH` / `Tracking Number:`.
SHIPPER_ABOVE_TRACKING_RE = re.compile(
    r"^\s*([A-Z][A-Z0-9 &.,'()/-]*?)\s*\n\s*Tracking Number:",
    re.MULTILINE,
)
# A label bought for a parcel you are sending.
LABEL_RE = re.compile(r"^UPS Label Delivery\b", re.IGNORECASE)
COLLECTION_RE = re.compile(r"^UPS Collection Request\b", re.IGNORECASE)
# The first line of the address block is the recipient's name.
SHIP_TO_RE = re.compile(r"^\s*Ship To:\s*\n\s*(\S.*?)\s*$", re.MULTILINE)


def label_parcel(tracking: str, blocks: str) -> dict:
    parcel: dict = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "provider": {"@type": "Organization", "@id": "ups", "name": "UPS"},
        "deliveryStatus": "Scheduled",
        "mailsift:direction": "outgoing",
    }
    m = SHIP_TO_RE.search(blocks)
    if m:
        parcel["deliveryAddress"] = {"@type": "PostalAddress", "name": m.group(1)}
    return parcel


def main() -> int:
    mail = read_message()
    if not mail.subject or COLLECTION_RE.match(mail.subject):
        return 0

    if mail.html:
        text = strip_html(mail.html, spaced=True)
    elif mail.text:
        text = mail.text
    else:
        return 0

    tracking_match = TRACKING_RE.search(text)
    if not tracking_match:
        return 0
    tracking = tracking_match.group(1)

    if LABEL_RE.match(mail.subject):
        blocks = strip_html(mail.html, block_tags=True) if mail.html else text
        Path(f"ups-{tracking}.parcel.json").write_text(
            json.dumps(label_parcel(tracking, blocks), ensure_ascii=False),
            encoding="utf-8",
        )
        return 0

    status = status_from_subject(mail.subject)

    parcel = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "provider": {"@type": "Organization", "@id": "ups", "name": "UPS"},
    }
    if status:
        parcel["deliveryStatus"] = status
    # The sender sits on its own line: `From GARMIN (EUROPE) LIMITED`.
    if mail.html:
        blocks = strip_html(mail.html, block_tags=True)
        sender_m = SENDER_RE.search(blocks) or SHIPPER_ABOVE_TRACKING_RE.search(blocks)
        if sender_m:
            parcel["merchant"] = {
                "@type": "Organization",
                "name": sender_m.group(1).strip(),
            }

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
