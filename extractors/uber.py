#!/usr/bin/env python3
"""Uber rideshare and Uber Eats receipts.

Receipts come from noreply@uber.com with subjects like:

- "[Personal] Your <Day> <part-of-day> trip with Uber"     -> rideshare
- "[Personal] Your <Day> <part-of-day> order with Uber Eats"
                                                           -> food order

The HTML body for both kinds has "Total <symbol><amount>" near the top
(possibly with a converted second line for trips abroad). Eats mails
also have "Here's your receipt for <merchant>" giving the restaurant.
Rideshare mails have "UberX <distance>, <duration>" and a couple of
geocoded address lines.

We can't reliably extract a unique order id from these mails (Uber's
internal xid is buried in the HTML head but not user-visible), so we
synthesise one from the message date + the merchant slug for Eats, or
from `uber-trip-<isotimestamp>` for rides. Duplicate suppression on the
Rust side then keys on whatever we produce.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message, strip_html

TOTAL_RE = re.compile(r"\bTotal\s*([£€$])\s*(\d+(?:[.,]\d{2})?)")
EATS_MERCHANT_RE = re.compile(
    r"Here'?s\s+your\s+receipt\s+for\s+(?P<merchant>[^.\n]+?)\s*[.\n]", re.IGNORECASE
)
SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}


def parse_amount(num: str) -> float:
    return float(num.replace(",", "."))


def detect_kind(subject: str) -> str | None:
    s = subject.lower()
    if "trip with uber" in s:
        return "trip"
    if "order with uber eats" in s or "uber eats" in s:
        return "eats"
    return None


def main() -> int:
    mail = read_message()
    if not mail.subject:
        return 0
    kind = detect_kind(mail.subject)
    if kind is None:
        return 0
    if not mail.html:
        return 0

    text = strip_html(mail.html, block_tags=True)
    total_m = TOTAL_RE.search(text)
    if not total_m:
        return 0
    # If the body shows both "Total <currency>" and a separate "Trip
    # fare <currency>" in different currencies, the trip fare is the
    # native one; for the receipt we want the amount the user was
    # charged, so we keep `Total`.
    total = parse_amount(total_m.group(2))
    currency = SYMBOL_TO_CURRENCY.get(total_m.group(1), "USD")

    if kind == "eats":
        merchant_m = EATS_MERCHANT_RE.search(text)
        merchant_name = (
            merchant_m.group("merchant").strip() if merchant_m else "Uber Eats"
        )
        merchant_slug = re.sub(r"[^a-z0-9]+", "-", merchant_name.lower()).strip("-")
        provider = "Uber Eats"
    else:
        merchant_name = "Uber"
        merchant_slug = "uber"
        provider = "Uber"

    # Synthesise a stable id from the message date and the slug - the
    # body itself never carries a customer-visible order number.
    if mail.date is None:
        order_id = f"{merchant_slug}-{kind}"
    else:
        order_id = f"{merchant_slug}-{mail.date.strftime('%Y%m%dT%H%M%S')}"

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": merchant_name,
        "broker": {"@type": "Organization", "name": provider},
        "orderNumber": f"uber-{kind}-{order_id}",
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": total,
            "priceCurrency": currency,
        },
    }
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")

    Path(f"uber-{kind}-{order_id}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
