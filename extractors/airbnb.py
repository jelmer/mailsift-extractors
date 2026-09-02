#!/usr/bin/env python3
"""Airbnb payment receipts.

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
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

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


def parse_amount(raw: str) -> float:
    return float(raw.replace(",", ""))


def main() -> int:
    mail = read_message()
    html = mail.html
    if not html:
        return 0
    text = strip_html(html)

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
