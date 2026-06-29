#!/usr/bin/env python3
"""Google Play receipt extractor.

Google Play sends a stable plaintext receipt format with:

    Order number: GPA.XXXX-XXXX-XXXX-XXXXX
    Order date: 19 Jun 2026 14:13:03 BST
    Your account: test@example.org
    ...
    Total: £1.59/month

Used for one-off purchases and recurring subscription renewals. We emit
a `.receipt.json` for each, loosely schema.org `Order`-shaped.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


ORDER_RE = re.compile(r"^Order number:\s*(GPA\.[\w.\-]+)", re.M)
DATE_RE = re.compile(r"^Order date:\s*(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{4})", re.M)
ITEM_RE = re.compile(
    r"\n\n([^\n]+?(?:\(by [^\)]+\))?)\n(?:£|€|\$)([0-9]+(?:\.[0-9]{1,2})?)"
)
TOTAL_RE = re.compile(r"^Total:\s*(£|€|\$)?\s*([0-9]+(?:\.[0-9]{1,2})?)", re.M)

MONTH_ABBR = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}


def main() -> int:
    mail = read_message()
    sender = (mail.from_address or "").lower()
    if "googleplay-noreply@google.com" not in sender:
        return 0
    text = mail.text or ""
    if not text:
        return 0

    order_m = ORDER_RE.search(text)
    if not order_m:
        return 0
    order_id = order_m.group(1)

    total_m = TOTAL_RE.search(text)
    if not total_m:
        return 0
    symbol = total_m.group(1) or ""
    currency = SYMBOL_TO_CURRENCY.get(symbol, "USD")
    amount = float(total_m.group(2))

    receipt = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "Google Play",
        "orderNumber": order_id,
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": amount,
            "priceCurrency": currency,
        },
    }

    date_m = DATE_RE.search(text)
    if date_m:
        try:
            order_date = datetime(
                int(date_m.group(3)),
                MONTH_ABBR[date_m.group(2)],
                int(date_m.group(1)),
            )
            receipt["orderDate"] = order_date.strftime("%Y-%m-%d")
        except (KeyError, ValueError):
            pass
    if "orderDate" not in receipt and mail.date is not None:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")

    # Slugify the order id for the filename. Google's order ids contain
    # dots (`GPA.0000-...`) and sometimes runs of them (`..3` in
    # subscription renewals); replace any non-alphanumeric run with a
    # single hyphen so the only `.` left in the filename is the one
    # separating slug from kind.
    slug = re.sub(r"[^A-Za-z0-9_+-]+", "-", order_id).strip("-")
    Path(f"google-play-{slug}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
