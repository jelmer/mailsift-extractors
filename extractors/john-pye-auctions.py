#!/usr/bin/env python3
"""John Pye Auctions invoice notifications.

Two lifecycle mails per won lot:

- `New Invoice #<NNN> from John Pye Auctions (JohnPye) for £<amount> GBP`
  when the lot is won and the invoice is issued.
- `Thank You - Invoice #<NNN> from John Pye Auctions (JohnPye) has been paid`
  after payment is settled.

Everything we need is in the subject: invoice number, and for the
`New Invoice` variant, the total amount + currency. Emit a receipt
on the `New Invoice` mail; the `Thank You` mail is redundant and
skipped.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

# `New Invoice #91247783 from John Pye Auctions (JohnPye) for £112.60 GBP`
NEW_INVOICE_RE = re.compile(
    r"New Invoice\s*#(?P<number>\d+)\s+from John Pye Auctions.*?"
    r"for\s*(?P<symbol>[£€$])?\s*(?P<amount>[0-9]+(?:\.[0-9]{2})?)\s+"
    r"(?P<currency>[A-Z]{3})",
    re.IGNORECASE,
)

SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}


def main() -> int:
    mail = read_message()
    subject = (mail.subject or "").strip()

    match = NEW_INVOICE_RE.search(subject)
    if not match:
        return 0

    invoice = match.group("number")
    amount = float(match.group("amount"))
    currency = match.group("currency")

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "John Pye Auctions",
        "orderNumber": invoice,
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": amount,
            "priceCurrency": currency,
        },
    }
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")

    Path(f"john-pye-auctions-{invoice}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
