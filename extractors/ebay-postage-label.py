#!/usr/bin/env python3
"""eBay "Your postage label is ready" mails, sent to the seller.

These are for a parcel you are sending, so they are filed as outgoing
(`mailsift:direction`). After tag-stripping, the order details read
one field per line:

    Post to
    <buyer name>
    <Town>, <postcode>
    ...
    Service
    Standard tracked delivery via Royal Mail | Drop-off
    Tracking
    VU000000000GB
    <item title>
    Order number
    00-00000-00000

The carrier is whatever follows "via" in the service line.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

POST_TO_RE = re.compile(
    r"^Post to\n(?P<name>.+)\n(?P<locality>.+?),\s*(?P<postcode>[A-Z0-9 ]+)$",
    re.MULTILINE,
)
# `... via InPost (including Yodel) | Drop-off`
SERVICE_RE = re.compile(
    r"^Service\n.*?\bvia (?P<carrier>[^|(\n]+?)\s*(?:\(.*?\))?\s*(?:\|.*)?$",
    re.MULTILINE,
)
TRACKING_RE = re.compile(
    r"^Tracking\n(?P<number>[A-Z0-9]{8,})\n(?:(?P<item>.+)\n)?Order number\n"
    r"(?P<order>\d{2}-\d{5}-\d{5})$",
    re.MULTILINE,
)
CARRIER_IDS = {
    "evri": "evri",
    "inpost": "inpost",
    "royal mail": "royal-mail",
    "parcelforce": "parcelforce",
    "dpd": "dpd",
    "yodel": "yodel",
}


def main() -> int:
    mail = read_message()
    if not mail.html:
        return 0
    # One field per line; the blank lines between blocks don't matter.
    lines = strip_html(mail.html, block_tags=True).splitlines()
    text = "\n".join(line.strip() for line in lines if line.strip())

    tracking_m = TRACKING_RE.search(text)
    if not tracking_m:
        return 0
    tracking = tracking_m.group("number")

    parcel: dict = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "deliveryStatus": "Scheduled",
        "mailsift:direction": "outgoing",
        "orderNumber": tracking_m.group("order"),
    }
    service_m = SERVICE_RE.search(text)
    if service_m:
        name = service_m.group("carrier").strip()
        provider = {"@type": "Organization"}
        carrier_id = CARRIER_IDS.get(name.lower())
        if carrier_id:
            provider["@id"] = carrier_id
        provider["name"] = name
        parcel["provider"] = provider
    post_to_m = POST_TO_RE.search(text)
    if post_to_m:
        parcel["deliveryAddress"] = {
            "@type": "PostalAddress",
            "name": post_to_m.group("name").strip(),
            "addressLocality": post_to_m.group("locality").strip(),
            "postalCode": post_to_m.group("postcode").strip(),
        }
    if tracking_m.group("item"):
        parcel["itemShipped"] = [
            {"@type": "Product", "name": tracking_m.group("item").strip()}
        ]

    Path(f"ebay-{tracking}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
