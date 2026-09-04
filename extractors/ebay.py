#!/usr/bin/env python3
"""eBay purchase confirmations and shipment updates.

eBay sends the buyer several notification mails per order:

- `Order confirmed: <item title>` right after checkout. Emits a
  `.receipt.json`. Free items and credit-covered orders are reported
  with `£0.00 total`; the subtotal captures the pre-credit price.
- `🚚 Order update: <item title>` when the seller ships. Carries a
  `Tracking number:` we route into a `.parcel.json`. eBay doesn't
  name the carrier in the mail body (only in link URLs), so the
  provider is recorded as `ebay` and downstream tracker sinks can
  chase the tracking number.

Sales notifications (`You made the sale for ...`) are ignored -
they're seller-side and not an artifact of a purchase or delivery
we're waiting on.

Bodies are HTML only, so we strip tags with a small HTMLParser and
regex the plain text out. eBay renders each field twice (once visible,
once for screen readers), so every regex is anchored to the first
occurrence.
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message

# Order number in the standard eBay `NN-NNNNN-NNNNN` shape.
ORDER_NUMBER_RE = re.compile(
    r"Order number:\s*\n\s*(?P<number>\d{2}-\d{5}-\d{5})", re.IGNORECASE
)
# Item ID: 12-digit numeric, appears right below `Item ID:`.
ITEM_ID_RE = re.compile(r"Item ID:\s*\n\s*(?P<id>\d{10,15})", re.IGNORECASE)
# Tracking number: on `Order update` mails, appears right below
# `Tracking number:`.
TRACKING_RE = re.compile(
    r"Tracking number:\s*\n\s*(?P<number>[A-Z0-9]{8,})", re.IGNORECASE
)
# `Total\n\n£0.00` on the summary panel. eBay always renders the
# currency symbol without a separator.
TOTAL_RE = re.compile(
    r"^Total\s*\n\s*(?P<symbol>[£€$])\s*(?P<amount>\d+(?:\.\d{2})?)\s*$",
    re.MULTILINE,
)
# `Subtotal\n£12.34` earlier in the summary. Useful when the total is
# £0.00 because the balance covered it.
SUBTOTAL_RE = re.compile(
    r"^Subtotal\s*\n\s*(?P<symbol>[£€$])\s*(?P<amount>\d+(?:\.\d{2})?)\s*$",
    re.MULTILINE,
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
        elif tag in ("br", "p", "div", "tr", "h1", "h2", "h3", "li"):
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


def first_item_title(text: str) -> str | None:
    """Item title appears once, right above the `Price:` line for
    purchases or right above `Item ID:` for updates. It doesn't have
    a labelled row, so we lift the line preceding `Item ID:`.
    """
    match = ITEM_ID_RE.search(text)
    if not match:
        return None
    prefix = text[: match.start()].rstrip()
    lines = [line.strip() for line in prefix.splitlines() if line.strip()]
    if not lines:
        return None
    # The title is the last non-empty line before `Item ID:`; if it's
    # the label `Price:` (purchase layout) walk further back past the
    # amount line.
    while lines and lines[-1].lower().startswith(("price:", "£", "€", "$")):
        lines.pop()
    return lines[-1] if lines else None


def emit_receipt(text: str, mail) -> bool:
    order_match = ORDER_NUMBER_RE.search(text)
    if not order_match:
        return False
    order_number = order_match.group("number")
    total_match = TOTAL_RE.search(text)
    subtotal_match = SUBTOTAL_RE.search(text)
    if not (total_match or subtotal_match):
        return False

    # Prefer the total, but fall back to the subtotal when the total
    # is 0 (eBay renders £0.00 when the balance credit covers the
    # whole order; the subtotal still captures the pre-credit price
    # which is what a receipt reader wants to see).
    total_is_zero = total_match and float(total_match.group("amount")) == 0
    price_source = (
        subtotal_match
        if (subtotal_match and (not total_match or total_is_zero))
        else total_match
    )
    assert price_source is not None
    receipt: dict = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": "eBay",
        "orderNumber": order_number,
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": float(price_source.group("amount")),
            "priceCurrency": SYMBOL_TO_CURRENCY.get(
                price_source.group("symbol"), "USD"
            ),
        },
    }
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")
    title = first_item_title(text)
    if title:
        receipt["orderedItem"] = [
            {
                "@type": "OrderItem",
                "orderedItem": {"@type": "Product", "name": title},
                "orderQuantity": 1,
            }
        ]
    Path(f"ebay-{order_number}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return True


def emit_parcel(text: str, mail) -> bool:
    track_match = TRACKING_RE.search(text)
    if not track_match:
        return False
    tracking_number = track_match.group("number")
    order_match = ORDER_NUMBER_RE.search(text)
    parcel: dict = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking_number,
        # eBay's `Order update` mails don't name the carrier in the
        # visible body (only in the tracking link URL, and the mapping
        # varies by seller). Leaving the provider generic here lets a
        # downstream tracker sink resolve it from the number.
        "provider": {"@type": "Organization", "@id": "ebay", "name": "eBay"},
    }
    if order_match:
        parcel["orderNumber"] = order_match.group("number")
    Path(f"ebay-{tracking_number}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )
    return True


def main() -> int:
    mail = read_message()
    subject = (mail.subject or "").lower()
    html = mail.html
    if not html:
        return 0
    text = strip_html(html)

    if "order confirmed" in subject:
        emit_receipt(text, mail)
    if "order update" in subject:
        emit_parcel(text, mail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
