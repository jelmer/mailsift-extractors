#!/usr/bin/env python3
"""Rapha cycling apparel order confirmations and dispatch mails.

- `Your Rapha order confirmation - Order <NNN>`: HTML-only, carries
  the order number, an itemised list with prices, and an order
  total. Emits a `.receipt.json`.
- `Your Rapha dispatch confirmation - Order <NNN>`: adds a tracking
  link URL (`https://track.dpd.co.uk/parcels/<NNN>`) that Rapha
  reuses for every carrier they've been shipping with. Emits a
  `.parcel.json` keyed on the tracking number.
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

ORDER_NUMBER_RE = re.compile(r"Order Number\s*\n\s*(?P<number>\d{6,12})")
# Order total on the confirmation mail; may appear multiple times in
# the HTML, we want the LAST one (final total after shipping).
TOTAL_RE = re.compile(
    r"ORDER TOTAL\s*\n\s*(?P<symbol>[£€$])?\s*(?P<amount>[0-9]+(?:\.[0-9]{2})?)",
    re.IGNORECASE,
)
# Tracking link on the dispatch mail. Rapha routes via various
# carriers; capture the tracking number embedded in the URL and
# infer the carrier from the URL host.
TRACKING_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:track|tracking)\.([a-z]+)\.[a-z.]+"
    r"/(?:parcels?|tracking|track)/?([A-Za-z0-9\-]+)",
    re.IGNORECASE,
)

SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}


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


def emit_receipt(mail, text: str) -> None:
    order_match = ORDER_NUMBER_RE.search(text)
    if not order_match:
        return
    totals = list(TOTAL_RE.finditer(text))
    if not totals:
        return
    total = totals[-1]  # last is the grand total
    order_number = order_match.group("number")

    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "Rapha",
        "orderNumber": order_number,
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": float(total.group("amount")),
            "priceCurrency": SYMBOL_TO_CURRENCY.get(
                total.group("symbol") or "£", "GBP"
            ),
        },
    }
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")
    Path(f"rapha-{order_number}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )


def emit_parcel(mail, text: str) -> None:
    # Look in the raw html for the tracking URL - the stripped text
    # loses `<a href>` targets, and we saw the URL in the plain form
    # too on dispatch mails.
    html = mail.html or ""
    url_match = TRACKING_URL_RE.search(html) or TRACKING_URL_RE.search(text)
    if not url_match:
        return
    carrier = url_match.group(1).lower()
    tracking = url_match.group(2)
    order_match = ORDER_NUMBER_RE.search(text)

    parcel: dict = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking,
        "provider": {
            "@type": "Organization",
            "@id": carrier,
            "name": carrier.upper() if len(carrier) <= 4 else carrier.capitalize(),
        },
        "merchant": "Rapha",
    }
    if order_match:
        parcel["orderNumber"] = order_match.group("number")
    Path(f"rapha-{tracking}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )


def main() -> int:
    mail = read_message()
    subject = (mail.subject or "").lower()
    if not mail.html:
        return 0
    text = strip_html(mail.html)

    if "order confirmation" in subject:
        emit_receipt(mail, text)
    if "dispatch confirmation" in subject:
        emit_parcel(mail, text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
