#!/usr/bin/env python3
"""DHL Express shipment notifications.

DHL Express sends a series of HTML-only status mails from
`noreply.odd@dhl.com` for each shipment: `Your Shipment Is On Its
Way`, `Your Shipment Is Arriving Soon`, `Your Delivery Is Today`,
`Your Shipment Has Been Delivered`. The body is heavily styled but
carries a stable `Waybill No.` line and (usually) the shipper's
name; the current status is inferred from the subject.

Emits one `.parcel.json` per mail keyed on the waybill; mailsift's
parcels target merges successive updates for the same waybill so
the record grows a `history` of status changes.
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

# `Waybill No.<number>` or `Waybill No.\n<number>`. Numeric, 8-14
# digits based on what we've seen.
WAYBILL_RE = re.compile(r"Waybill No\.\s*\n?\s*(\d{8,14})", re.IGNORECASE)
# "Your DHL Express shipment with waybill number NNN from SHIPPER" -
# the inline "from SHIPPER" variant on the first-status mail. The
# shipper name runs up to the next sentence break.
FROM_INLINE_SHIPPER_RE = re.compile(
    r"from\s+(?P<shipper>[A-Z][A-Z0-9 &.,'\-]*?)\s+is on its way", re.IGNORECASE
)
# `Shipper Name\n<name>` on the later-status mails.
SHIPPER_NAME_LABEL_RE = re.compile(r"Shipper Name\s*\n\s*([A-Z][A-Z0-9 &.,'\-]+?)\s*\n")

# Subject -> canonical delivery status. Ordered so the most-final
# state wins if the subject is ambiguous.
SUBJECT_TO_STATUS = [
    ("has been delivered", "OrderDelivered"),
    ("delivery is today", "OrderInTransit"),
    ("is arriving soon", "OrderInTransit"),
    ("is on its way", "OrderInTransit"),
]


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self.skip = True
        elif tag in ("br", "p", "div", "tr", "h1", "h2", "h3", "li", "td"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self.skip = False

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(html: str) -> str:
    p = _Strip()
    p.feed(html)
    text = "".join(p.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def status_from_text(*strings: str) -> str | None:
    """Return the canonical status inferred from any of the strings.

    Some early-status mails carry a generic subject
    (`DHL On Demand Delivery`) with the actual banner phrase in the
    body, so we scan both subject and stripped body text.
    """
    combined = " ".join(s.lower() for s in strings if s)
    for needle, status in SUBJECT_TO_STATUS:
        if needle in combined:
            return status
    return None


def shipper_from_text(text: str) -> str | None:
    # Prefer the labelled shipper (later-status mails carry it in a
    # panel); fall back to the inline `from SHIPPER is on its way`.
    label_match = SHIPPER_NAME_LABEL_RE.search(text)
    if label_match:
        return label_match.group(1).strip()
    inline_match = FROM_INLINE_SHIPPER_RE.search(text)
    if inline_match:
        return inline_match.group("shipper").strip()
    return None


def main() -> int:
    mail = read_message()
    subject = (mail.subject or "").strip()
    html = mail.html
    if not html:
        return 0
    text = strip_html(html)

    status = status_from_text(subject, text)
    if status is None:
        return 0

    waybill_match = WAYBILL_RE.search(text)
    if not waybill_match:
        return 0
    waybill = waybill_match.group(1)

    parcel: dict = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": waybill,
        "deliveryStatus": status,
        "provider": {"@type": "Organization", "@id": "dhl", "name": "DHL Express"},
    }
    shipper = shipper_from_text(text)
    if shipper:
        parcel["merchant"] = shipper

    Path(f"dhl-{waybill}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
