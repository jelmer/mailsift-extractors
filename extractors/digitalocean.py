#!/usr/bin/env python3
"""DigitalOcean monthly payment receipts.

`DigitalOcean - Received $<amount> payment` mails from
`support@digitalocean.com` announce the monthly card charge. The
plain-text body is short and regular:

    Payment Receipt for My Team
    -----------------------------------------------------
    DigitalOcean Receipt - 01-Sep-2026
    Amount: $28.8
    ...

Emit a receipt keyed on the receipt date (DO's mail carries no
invoice id; the date is the identifier). Amount currency comes
from the leading symbol; DO invoices in USD by default but may
switch to another currency in future so we don't hardcode.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

# `DigitalOcean Receipt - 01-Sep-2026` - the dash-separated date is
# the closest thing to an invoice id in the body.
RECEIPT_DATE_RE = re.compile(
    r"DigitalOcean Receipt\s*-\s*(\d{2})-([A-Z][a-z]{2})-(\d{4})"
)
# `Amount: $28.8` - single-currency line, `$` for USD, `€` for EUR,
# `£` for GBP.
AMOUNT_RE = re.compile(r"Amount:\s*([£€$])\s*([0-9]+(?:\.[0-9]{1,2})?)")
SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}
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


def main() -> int:
    mail = read_message()
    text = mail.text or ""
    if not text:
        return 0

    date_match = RECEIPT_DATE_RE.search(text)
    amount_match = AMOUNT_RE.search(text)
    if not (date_match and amount_match):
        return 0

    day, mon, year = date_match.groups()
    month = MONTH_ABBR.get(mon)
    if month is None:
        return 0
    try:
        receipt_date = datetime(int(year), month, int(day))
    except ValueError:
        return 0

    amount = float(amount_match.group(2))
    currency = SYMBOL_TO_CURRENCY.get(amount_match.group(1), "USD")

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "DigitalOcean",
        "orderNumber": receipt_date.strftime("%Y-%m-%d"),
        "orderDate": receipt_date.strftime("%Y-%m-%d"),
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": amount,
            "priceCurrency": currency,
        },
    }
    Path(f"digitalocean-{receipt_date.strftime('%Y-%m-%d')}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
