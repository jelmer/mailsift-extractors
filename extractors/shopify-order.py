#!/usr/bin/env python3
"""Generic Shopify-templated order confirmations.

Many Shopify-hosted shops use the stock notification templates almost
unchanged. They produce two mail types we care about:

- Order confirmation: subject like `Order #100002 confirmed`. Plain
  text body carries `Order #<id>`, an order summary table with item
  lines and a `Total\\n\\n£42.30 GBP`-style line. Emit a
  `.receipt.json`.
- Shipment notification: subject like `A shipment from order #<id> is
  on the way`. Body carries the same order id plus a line
  `<Carrier> tracking number: <number>`. Emit a `.parcel.json`.

The merchant name is taken from the `From:` display name or domain.
The manifest restricts which `from_domains` we run on, so we don't
have to recognise every shop.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from mailsift_extractor import read_message  # noqa: E402


ORDER_ID_RE = re.compile(r"Order\s+#([A-Za-z0-9]+)")
# Item line in the order-summary table: "Product name × 1" then a
# blank line then "£12.34". Names can contain almost anything except a
# newline; the × is unicode U+00D7 in the wire template.
ITEM_RE = re.compile(
    r"^(?P<name>.+?)\s*[×x]\s*(?P<qty>\d+)\s*\n\s*\n(?P<symbol>[£€$])(?P<price>[0-9]+(?:\.[0-9]{2})?)",
    re.M,
)
# Final "Total" line: `Total\n\n£42.30 GBP` - the currency suffix is
# what disambiguates the line from the subtotal.
TOTAL_RE = re.compile(
    r"^Total\s*\n\s*\n(?P<symbol>[£€$])(?P<price>[0-9]+(?:\.[0-9]{2})?)\s+(?P<currency>[A-Z]{3})",
    re.M,
)
# Carrier tracking line. The label varies (`DPD tracking number`,
# `Special Care tracking number`, `Royal Mail tracking number`, ...);
# the value is alphanumeric. Restrict the carrier label to non-newline
# whitespace so we don't slurp surrounding lines.
TRACKING_RE = re.compile(
    r"^(?P<carrier>[A-Za-z][A-Za-z0-9 ]*?)\s+tracking\s+number:\s*(?P<number>[A-Za-z0-9]+)",
    re.M | re.I,
)

SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}

# Map the parsed carrier label (as it appears in the body) to our
# canonical carrier ids. Anything we don't recognise gets the slugged
# carrier name verbatim so the parcels target still has *something*.
CARRIER_MAP = {
    "dpd": "dpd",
    "royal mail": "royal-mail",
    "special care": "royal-mail",  # The Pi Hut's "Special Care" is Royal Mail Tracked
}


def merchant_from_address(from_address: str | None) -> str:
    """Pull a short merchant name from the sender's domain."""
    if not from_address:
        return "Shop"
    domain = from_address.rsplit("@", 1)[-1].lower()
    # `contact@thepihut.com` -> "thepihut.com" -> "Thepihut".
    # `help@patchplants.com` -> "patchplants.com" -> "Patchplants".
    bare = domain.split(".")[0]
    return bare.capitalize()


def emit_receipt(text: str, mail) -> bool:
    order_m = ORDER_ID_RE.search(text)
    total_m = TOTAL_RE.search(text)
    if not (order_m and total_m):
        return False
    order_id = order_m.group(1)
    merchant = merchant_from_address(mail.from_address)
    items = []
    for item_m in ITEM_RE.finditer(text):
        items.append(
            {
                "@type": "OrderItem",
                "orderedItem": {
                    "@type": "Product",
                    "name": item_m.group("name").strip(),
                },
                "orderQuantity": int(item_m.group("qty")),
                "orderItemSubtotal": {
                    "@type": "PriceSpecification",
                    "price": float(item_m.group("price")),
                    "priceCurrency": SYMBOL_TO_CURRENCY.get(
                        item_m.group("symbol"), "USD"
                    ),
                },
            }
        )
    receipt = {
        "@context": "https://schema.org",
        "@type": "Order",
        "merchant": merchant,
        "orderNumber": order_id,
        "priceSpecification": {
            "@type": "PriceSpecification",
            "price": float(total_m.group("price")),
            "priceCurrency": total_m.group("currency"),
        },
    }
    if mail.date:
        receipt["orderDate"] = mail.date.strftime("%Y-%m-%d")
    if items:
        receipt["orderedItem"] = items
    slug = merchant.lower()
    Path(f"{slug}-{order_id}.receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )
    return True


def emit_parcel(text: str, mail) -> bool:
    order_m = ORDER_ID_RE.search(text)
    track_m = TRACKING_RE.search(text)
    if not track_m:
        return False
    carrier_label = track_m.group("carrier").strip().lower()
    carrier_id = CARRIER_MAP.get(carrier_label, carrier_label.replace(" ", "-"))
    tracking_number = track_m.group("number")
    merchant = merchant_from_address(mail.from_address)

    parcel = {
        "@context": "https://schema.org",
        "@type": "ParcelDelivery",
        "trackingNumber": tracking_number,
        "provider": {
            "@type": "Organization",
            "@id": carrier_id,
            "name": track_m.group("carrier").strip(),
        },
    }
    if order_m:
        parcel["orderNumber"] = order_m.group(1)
    parcel["merchant"] = merchant

    Path(f"{merchant.lower()}-{tracking_number}.parcel.json").write_text(
        json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
    )
    return True


def main() -> int:
    mail = read_message()
    subject = (mail.subject or "").strip()
    text = mail.text or ""
    if not text:
        return 0

    subject_lower = subject.lower()
    emitted_any = False
    # Order confirmation: `Order #N confirmed` (also seen: `Thank you
    # for your order!`, `Order confirmation`).
    if "confirmed" in subject_lower or "thank you for your order" in subject_lower:
        emitted_any |= emit_receipt(text, mail)
    # Shipment: `A shipment from order #N is on the way`.
    if "on the way" in subject_lower or "shipped" in subject_lower:
        emitted_any |= emit_parcel(text, mail)
    # Some shops collapse confirmation and shipping into a single
    # "Order X has been delivered" mail; treat as parcel update.
    if "has been delivered" in subject_lower:
        emitted_any |= emit_parcel(text, mail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
