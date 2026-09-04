#!/usr/bin/env python3
"""DigitalOcean monthly invoice mail.

`support@digitalocean.com` sends a `[DigitalOcean] Your YYYY-MM invoice
is available` mail on the first of each month with the PDF invoice
attached. The body is a plain-text summary of the balance and totals;
the balance is auto-charged before the mail is sent, so this mail is
functionally a paid receipt with a PDF attached.

We already have `digitalocean.py` for the separate `Received $X
payment` mail (which carries no PDF). This extractor handles the
invoice mail and preserves the attached PDF as a `.receipt.pdf`
sidecar to the JSON.

Body extract:

    Your 2026-06 invoice is now available
    ...
    Usage charges for 2026-06:                          $24.00
    Tax (Taxes):                                         $4.80
    Invoice Total:                                      $28.80
    Amount paid:                                       -$28.80

The invoice period (`2026-06`) is the natural identifier - DO's PDF
filename contains a customer id + serial that we don't need.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

PERIOD_RE = re.compile(r"Your\s+(\d{4}-\d{2})\s+invoice", re.IGNORECASE)
TOTAL_RE = re.compile(
    r"Invoice Total:\s*([£€$])\s*([0-9]+(?:\.[0-9]{1,2})?)", re.IGNORECASE
)
SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}


def main() -> int:
    mail = read_message()
    text = mail.text or ""
    if not text:
        return 0

    period_m = PERIOD_RE.search(text)
    total_m = TOTAL_RE.search(text)
    if not (period_m and total_m):
        return 0

    period = period_m.group(1)  # e.g. "2026-06"
    amount = float(total_m.group(2))
    currency = SYMBOL_TO_CURRENCY.get(total_m.group(1), "USD")

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "DigitalOcean",
        "orderNumber": period,
        "orderDate": mail.date.strftime("%Y-%m-%d") if mail.date else f"{period}-01",
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": amount,
            "priceCurrency": currency,
        },
    }
    slug = f"digitalocean-invoice-{period}"
    Path(f"{slug}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )

    pdf = mail.find_pdf_attachment("digitalocean invoice")
    if pdf is not None:
        Path(f"{slug}.receipt.pdf").write_bytes(pdf.bytes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
