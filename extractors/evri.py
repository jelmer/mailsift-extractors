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
from the subject ("We've got your <merchant> parcel", "Your <merchant>
parcel is out for delivery", ...).

"Thanks for dropping off your parcel" confirms a parcel you are
sending, not one coming to you. It is filed as an outgoing parcel
(`mailsift:direction`), handed over to Evri and so on its way. The
mail names neither the recipient nor a merchant: the "<X> parcel" in
its body is the service the label was bought through ("eBay Simple
Delivery").
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

# Evri tracking numbers are 16 letters and digits (`H0000A0000000000`,
# `T00N3A0022795218`), on their own after a "Tracking number" label.
TRACKING_RE = re.compile(r"\bTracking number:?\s+([A-Z0-9]{16})\b")
URL_TRACKING_RE = re.compile(
    r"evri\.com/track/(?:#/)?parcel/([A-Z0-9]{10,20})", re.IGNORECASE
)
_APOSTROPHE = "['\u2019]"
# Subject templates naming the sender, with the status each implies. A
# parcel waiting at a ParcelShop counts as out for delivery, as doorstep
# has it for DPD.
SUBJECT_PATTERNS: list[tuple[str, str]] = [
    (r"Thanks for collecting your (?P<merchant>.+) parcel", "Delivered"),
    (rf"We{_APOSTROPHE}ve delivered your (?P<merchant>.+) parcel", "Delivered"),
    (r"Evri has successfully delivered your (?P<merchant>.+) parcel", "Delivered"),
    (r"Your (?P<merchant>.+) parcel is out for delivery", "OutForDelivery"),
    (r"Your (?P<merchant>.+) parcel is now with your local \w+ courier.*", "OnItsWay"),
    (rf"We{_APOSTROPHE}ve got your (?P<merchant>.+) parcel", "OnItsWay"),
    (rf"We{_APOSTROPHE}re expecting your (?P<merchant>.+) parcel", "Scheduled"),
    (r"Your (?P<merchant>.+) parcel is ready to collect", "OutForDelivery"),
    (r"Remember to collect your (?P<merchant>.+) parcel", "OutForDelivery"),
    (
        rf"Sorry, we couldn{_APOSTROPHE}t deliver your (?P<merchant>.+) parcel.*",
        "OrderProblem",
    ),
]
SUBJECT_RES = [
    (re.compile(rf"^{pattern}\s*$", re.IGNORECASE), status)
    for pattern, status in SUBJECT_PATTERNS
]
OUTGOING_RE = re.compile(r"^Thanks for dropping off your\b", re.IGNORECASE)


def status_and_merchant(subject: str) -> tuple[str | None, str | None]:
    s = subject.strip()
    for pattern, status in SUBJECT_RES:
        m = pattern.match(s)
        if m:
            return status, m.group("merchant").strip()
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
    outgoing = OUTGOING_RE.match(mail.subject) is not None
    if mail.html:
        text = strip_html(mail.html, spaced=True)
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

    status: str | None
    merchant: str | None
    if outgoing:
        status, merchant = "OnItsWay", None
    else:
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
    if outgoing:
        parcel["mailsift:direction"] = "outgoing"

    Path(f"evri-{tracking}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
