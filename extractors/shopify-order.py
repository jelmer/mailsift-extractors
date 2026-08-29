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

from mailsift_extractor import read_message

ORDER_ID_RE = re.compile(r"Order\s+#([A-Za-z0-9]+)")
# Item line in the order-summary table: "Product name × 1" then a
# blank line then "£12.34". Names can contain almost anything except a
# newline; the × is unicode U+00D7 in the wire template.
ITEM_RE = re.compile(
    r"^(?P<name>.+?)\s*[×x]\s*(?P<qty>\d+)\s*\n\s*\n(?P<symbol>[£€$])(?P<price>[0-9]+(?:\.[0-9]{2})?)",
    re.MULTILINE,
)
# Final "Total" line: `Total\n\n£42.30 GBP` - the currency suffix is
# what disambiguates the line from the subtotal.
TOTAL_RE = re.compile(
    r"^Total\s*\n\s*\n(?P<symbol>[£€$])(?P<price>[0-9]+(?:\.[0-9]{2})?)\s+(?P<currency>[A-Z]{3})",
    re.MULTILINE,
)
# Carrier tracking line. The label varies (`DPD tracking number`,
# `Special Care tracking number`, `Royal Mail tracking number`, ...)
# and some shops drop it entirely, leaving a bare `Tracking number:`.
# Restrict the carrier label to non-newline whitespace so we don't
# slurp surrounding lines. Tracking numbers may carry hyphens
# (Evri) alongside alphanumerics.
TRACKING_RE = re.compile(
    r"^(?:(?P<carrier>[A-Za-z][A-Za-z0-9 ]*?)\s+)?tracking\s+number:\s*\n?\s*(?P<number>[A-Za-z0-9][A-Za-z0-9-]*)",
    re.MULTILINE | re.IGNORECASE,
)

SYMBOL_TO_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD"}

# Map the parsed carrier label (as it appears in the body) to our
# canonical carrier ids. Anything we don't recognise gets the slugged
# carrier name verbatim so the parcels target still has *something*.
CARRIER_MAP = {
    "dpd": "dpd",
    "royal mail": "royal-mail",
    "special care": "royal-mail",  # The Pi Hut's "Special Care" is Royal Mail Tracked
    "evri": "evri",
    "hermes": "evri",
    "yodel": "yodel",
    "parcelforce": "parcelforce",
    "postnl": "postnl",
    "ups": "ups",
    "fedex": "fedex",
    "dhl": "dhl",
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


def delivery_status(subject: str) -> str | None:
    """Map the Shopify notification subject onto a delivery status."""
    low = subject.lower()
    if "has been delivered" in low or "was delivered" in low:
        return "Delivered"
    if "out for delivery" in low:
        return "OutForDelivery"
    if "on the way" in low or "shipped" in low or "on its way" in low:
        return "InTransit"
    return None


def emit_parcel(text: str, mail) -> bool:
    """Emit one `.parcel.json` per tracking number in the mail.

    Shopify splits an order across shipments and repeats the tracking
    block for each one, so a single mail can carry several parcels.
    Downstream dedup keys on `trackingNumber`, which means every
    shipment needs its own file or the extras are lost.
    """
    order_m = ORDER_ID_RE.search(text)
    merchant = merchant_from_address(mail.from_address)
    status = delivery_status(mail.subject or "")

    seen: set[str] = set()
    for track_m in TRACKING_RE.finditer(text):
        tracking_number = track_m.group("number")
        if tracking_number in seen:
            continue
        seen.add(tracking_number)

        carrier_name = (track_m.group("carrier") or "").strip()
        if carrier_name:
            carrier_id = CARRIER_MAP.get(
                carrier_name.lower(), carrier_name.lower().replace(" ", "-")
            )
        else:
            carrier_id = None

        parcel = {
            "@context": "https://schema.org",
            "@type": "ParcelDelivery",
            "trackingNumber": tracking_number,
        }
        if carrier_id:
            parcel["provider"] = {
                "@type": "Organization",
                "@id": carrier_id,
                "name": carrier_name,
            }
        if order_m:
            parcel["orderNumber"] = order_m.group(1)
        if status:
            parcel["deliveryStatus"] = status
        parcel["merchant"] = {"@type": "Organization", "name": merchant}

        Path(f"{merchant.lower()}-{tracking_number}.parcel.json").write_text(
            json.dumps(parcel, ensure_ascii=False), encoding="utf-8"
        )
    return bool(seen)


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
    # Shipment: `A shipment from order #N is on the way`, plus the
    # later status updates Shopify sends against the same order
    # ("out for delivery", "has been delivered").
    if any(
        phrase in subject_lower
        for phrase in (
            "on the way",
            "on its way",
            "shipped",
            "out for delivery",
            "has been delivered",
            "was delivered",
        )
    ):
        emitted_any |= emit_parcel(text, mail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
