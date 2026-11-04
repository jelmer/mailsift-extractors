#!/usr/bin/env python3
"""Airbnb payment receipts and host cancellations.

`Your receipt from Airbnb` mails are HTML-only and carry no
schema.org markup (unlike the `Reservation confirmed for ...` mails
which the generic `schema-ld` extractor already handles). The
stripped body follows a stable layout:

    Receipt ID: RC4SJAWQ8N * 12 March 2021
    Greater London
    ...
    Confirmation code: HMXDKTZEKP
    ...
    Amount paid (GBP)
    £834.50

We emit a receipt keyed on the Receipt ID; the confirmation code
carries over so a downstream reader can join it back to the
reservation the `schema-ld` path produced from the confirmation
mail.

"Your 2021-04-30 reservation was cancelled" mails (sent when the host
cancels) have no markup either. They give the check-in date in the
subject, the listing in a `Host of <listing> in <city>` line and the
check-out date in the "Show homes" search link. The confirmation code
only appears inside the compensation coupon code, `HCP2-<code>`. We
emit the same `LodgingReservation` schema-ld filed from the
confirmation, with `reservationStatus: ReservationCancelled`.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

RECEIPT_ID_RE = re.compile(r"Receipt ID:\s*([A-Z0-9]{6,20})", re.IGNORECASE)
CONFIRMATION_RE = re.compile(r"Confirmation code:\s*([A-Z0-9]{6,20})", re.IGNORECASE)
# `Amount paid (GBP)\n£834.50` or `Amount paid (EUR)\n€100.00`.
# Airbnb also inflects to "Amount refunded" for cancellations; we
# accept either but keep the sign of the number the receipt gives.
AMOUNT_RE = re.compile(
    r"Amount (?:paid|refunded) \((?P<currency>[A-Z]{3})\)\s*\n\s*"
    r"(?P<symbol>[£€$])?\s*(?P<amount>-?[0-9,]+(?:\.[0-9]{2})?)",
)
# Fallback: `Total (GBP)\n£834.50` for older / different receipt
# layouts that skip the `Amount paid` line.
TOTAL_RE = re.compile(
    r"(?:New t|T)otal \((?P<currency>[A-Z]{3})\)\s*\n\s*"
    r"(?P<symbol>[£€$])?\s*(?P<amount>[0-9,]+(?:\.[0-9]{2})?)",
)

CANCELLED_SUBJECT_RE = re.compile(
    r"^Your (\d{4}-\d{2}-\d{2}) reservation was cancel+ed$", re.IGNORECASE
)
LISTING_RE = re.compile(r"^Host of (.+) in .+$")
COUPON_CODE_RE = re.compile(r"\bHCP\d+-([A-Z0-9]{6,20})\b")
CHECKOUT_RE = re.compile(r"[?&](?:amp;)?checkout=(\d{4}-\d{2}-\d{2})\b")


def parse_amount(raw: str) -> float:
    return float(raw.replace(",", ""))


def cancelled_reservation(html: str, checkin: date) -> dict:
    lines = [
        line.strip()
        for line in strip_html(html, block_tags=True).splitlines()
        if line.strip()
    ]
    listing = next(
        (m.group(1) for line in lines if (m := LISTING_RE.match(line))), None
    )
    if listing is None:
        raise ValueError("cancellation without a 'Host of <listing>' line")
    code_m = COUPON_CODE_RE.search(html)
    if not code_m:
        raise ValueError(f"cancellation of {listing!r} has no confirmation code")
    checkout_m = CHECKOUT_RE.search(html)
    if not checkout_m:
        raise ValueError(f"cancellation of {listing!r} has no check-out date")
    return {
        "@context": "https://schema.org",
        "@type": "LodgingReservation",
        "reservationStatus": "ReservationCancelled",
        "reservationNumber": code_m.group(1),
        "checkinTime": checkin.isoformat(),
        "checkoutTime": date.fromisoformat(checkout_m.group(1)).isoformat(),
        "reservationFor": {"@type": "LodgingBusiness", "name": listing},
    }


def main() -> int:
    mail = read_message()
    html = mail.html
    if not html:
        return 0

    cancelled_m = CANCELLED_SUBJECT_RE.match((mail.subject or "").strip())
    if cancelled_m:
        res = cancelled_reservation(html, date.fromisoformat(cancelled_m.group(1)))
        Path(f"airbnb-{res['reservationNumber']}.reservation.json").write_text(
            json.dumps(res, ensure_ascii=False), encoding="utf-8"
        )
        return 0

    text = strip_html(html, block_tags=True)

    receipt_match = RECEIPT_ID_RE.search(text)
    if not receipt_match:
        return 0
    receipt_id = receipt_match.group(1)

    amount_match = AMOUNT_RE.search(text) or TOTAL_RE.search(text)
    if not amount_match:
        return 0

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "Airbnb",
        "orderNumber": receipt_id,
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": parse_amount(amount_match.group("amount")),
            "priceCurrency": amount_match.group("currency"),
        },
    }
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")

    confirmation_match = CONFIRMATION_RE.search(text)
    if confirmation_match:
        # Cross-link back to the schema-ld-emitted reservation:
        # the confirmation code is the reservation's own
        # `reservationNumber`.
        receipt["confirmationNumber"] = confirmation_match.group(1)

    Path(f"airbnb-{receipt_id}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
